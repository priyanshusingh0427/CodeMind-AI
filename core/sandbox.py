"""Isolated execution of tests in a locked-down Docker container.

CodeMind AI never runs submitted or AI-generated code directly on the host.
Dynamic execution happens only through :class:`DockerSandbox`, which starts a
throw-away container with:

* ``--network none``                  no network access
* ``--user 65534:65534``              non-root (nobody) user
* ``--cpus`` / ``--memory`` / ``--pids-limit``  CPU, memory and process limits
* ``--read-only`` + small ``--tmpfs /tmp``     restricted, read-only filesystem
* ``--cap-drop ALL`` + ``no-new-privileges``   no Linux capabilities
* a single read-only bind mount of a fresh temporary directory (no sensitive
  host paths), a hard wall-clock timeout and output size limits.

If Docker or the sandbox image is unavailable, :meth:`DockerSandbox.status`
reports it and the application stays in static-analysis-only mode.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config import SANDBOX_DIR, Settings
from utils.helpers import truncate
from utils.logger import get_logger

logger = get_logger("sandbox")

RESULT_MARKER = "@@CODEMIND_RESULT@@"


@dataclass
class SandboxStatus:
    available: bool
    message: str
    docker_installed: bool = False
    daemon_running: bool = False
    image_present: bool = False


@dataclass
class TestCaseResult:
    __test__ = False  # not a pytest test class

    name: str
    outcome: str  # passed | failed | error | skipped
    message: str = ""
    duration: float = 0.0


@dataclass
class SandboxResult:
    """Outcome of running a test file against code in the sandbox."""

    executed: bool
    passed: int = 0
    failed: int = 0
    errors: int = 0
    cases: list[TestCaseResult] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration: float = 0.0
    error: str = ""

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors

    @property
    def all_passed(self) -> bool:
        return self.executed and self.total > 0 and self.failed == 0 and self.errors == 0

    def failure_summary(self, limit: int = 3000) -> str:
        parts = [f"{c.name}: {c.outcome}\n{c.message}" for c in self.cases if c.outcome != "passed"]
        if self.error:
            parts.insert(0, self.error)
        return truncate("\n\n".join(parts), limit)


class DockerSandbox:
    """Run pytest files against candidate code inside a hardened container."""

    def __init__(self, settings: Settings, docker_binary: Optional[str] = None) -> None:
        self.settings = settings
        self.docker = docker_binary or shutil.which("docker") or "docker"

    # -- availability -------------------------------------------------------
    def _run_docker(self, args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
        return subprocess.run([self.docker, *args], capture_output=True, text=True, timeout=timeout, check=False)

    def status(self) -> SandboxStatus:
        """Check docker CLI, daemon and sandbox image."""
        if not self.settings.sandbox_enabled:
            return SandboxStatus(False, "Sandbox disabled in settings: static-analysis-only mode.")
        if shutil.which(self.docker) is None and not Path(self.docker).exists():
            return SandboxStatus(False, "Docker is not installed: static-analysis-only mode.")
        try:
            info = self._run_docker(["info", "--format", "{{.ServerVersion}}"])
        except (subprocess.TimeoutExpired, OSError) as exc:
            return SandboxStatus(False, f"Docker is not responding ({exc.__class__.__name__}).", True)
        if info.returncode != 0:
            return SandboxStatus(False, "Docker daemon is not running: start Docker Desktop / dockerd.", True)
        try:
            image = self._run_docker(["image", "inspect", self.settings.sandbox_image])
        except (subprocess.TimeoutExpired, OSError) as exc:
            return SandboxStatus(False, f"Could not inspect image ({exc.__class__.__name__}).", True, True)
        if image.returncode != 0:
            return SandboxStatus(False, f"Sandbox image '{self.settings.sandbox_image}' not built. Build it from "
                                        "Settings or run `docker build -t codemind-sandbox:latest sandbox/`.",
                                 True, True, False)
        return SandboxStatus(True, "Docker sandbox ready.", True, True, True)

    def build_image(self, timeout: int = 600) -> tuple[bool, str]:
        """Build the sandbox image from ``sandbox/Dockerfile``."""
        try:
            result = self._run_docker(["build", "-t", self.settings.sandbox_image, str(SANDBOX_DIR)],
                                      timeout=timeout)
        except (subprocess.TimeoutExpired, OSError) as exc:
            return False, f"Image build failed: {exc}"
        output = truncate((result.stdout + result.stderr).strip(), 4000)
        return result.returncode == 0, output

    # -- execution ----------------------------------------------------------
    def build_command(self, workdir: str, container_name: str) -> list[str]:
        """Return the hardened ``docker run`` command (exposed for testing/docs)."""
        memory = f"{max(64, self.settings.sandbox_memory_mb)}m"
        return [
            self.docker, "run", "--rm", "--name", container_name,
            "--network", "none",
            "--user", "65534:65534",
            "--cpus", str(max(0.1, self.settings.sandbox_cpus)),
            "--memory", memory, "--memory-swap", memory,
            "--pids-limit", "64",
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--ulimit", "fsize=10485760:10485760",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-e", "HOME=/tmp",
            "-v", f"{workdir}:/work:ro",
            "-w", "/work",
            self.settings.sandbox_image,
            "python", "/work/runner.py",
        ]

    def run_tests(self, code: str, test_code: str) -> SandboxResult:
        """Execute ``test_code`` (pytest) against ``code`` saved as ``solution.py``."""
        status = self.status()
        if not status.available:
            return SandboxResult(executed=False, error=status.message)

        container_name = f"codemind-{uuid.uuid4().hex[:10]}"
        workdir = tempfile.mkdtemp(prefix="codemind_sbx_")
        started = time.perf_counter()
        try:
            self._prepare_workdir(workdir, code, test_code)
            command = self.build_command(workdir, container_name)
            try:
                completed = subprocess.run(command, capture_output=True, text=True,
                                           timeout=self.settings.sandbox_timeout + 15, check=False)
            except subprocess.TimeoutExpired:
                self._kill(container_name)
                return SandboxResult(executed=True, timed_out=True, errors=1, duration=time.perf_counter() - started,
                                     error=f"Execution exceeded the {self.settings.sandbox_timeout}s time limit.")
            return self.parse_output(completed.stdout, completed.stderr, completed.returncode,
                                     time.perf_counter() - started)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def _prepare_workdir(self, workdir: str, code: str, test_code: str) -> None:
        base = Path(workdir)
        (base / "solution.py").write_text(code, encoding="utf-8")
        (base / "test_solution.py").write_text(self._with_timeout_guard(test_code), encoding="utf-8")
        shutil.copy(SANDBOX_DIR / "runner.py", base / "runner.py")
        os.chmod(base, 0o755)
        for item in base.iterdir():
            os.chmod(item, 0o644)

    def _with_timeout_guard(self, test_code: str) -> str:
        """Prepend an in-container alarm so runaway code stops even inside Python."""
        seconds = max(1, int(self.settings.sandbox_timeout))
        guard = ("import signal as _cm_signal\n"
                 "if hasattr(_cm_signal, 'SIGALRM'):\n"
                 f"    _cm_signal.alarm({seconds})\n")
        return guard + test_code

    def _kill(self, container_name: str) -> None:
        try:
            self._run_docker(["kill", container_name], timeout=10)
        except (subprocess.TimeoutExpired, OSError):
            logger.warning("could not kill container", extra={"container": container_name})

    def parse_output(self, stdout: str, stderr: str, returncode: int, duration: float) -> SandboxResult:
        """Parse the runner's JSON summary from container output."""
        limit = self.settings.sandbox_output_limit
        clean_stdout = stdout
        summary: Optional[dict] = None
        if RESULT_MARKER in stdout:
            pieces = stdout.split(RESULT_MARKER)
            if len(pieces) >= 3:
                try:
                    summary = json.loads(pieces[-2])
                except json.JSONDecodeError:
                    summary = None
                clean_stdout = pieces[0] + "".join(pieces[3:])
        result = SandboxResult(executed=True, stdout=truncate(clean_stdout, limit), stderr=truncate(stderr, limit),
                               duration=duration)
        if summary is None:
            if returncode == 137:
                result.error = "Container was killed (memory limit exceeded or timeout)."
            else:
                result.error = f"Sandbox produced no test summary (exit code {returncode})."
            result.errors = 1
            return result
        if "fatal" in summary:
            result.error = str(summary["fatal"])
            result.errors = 1
            return result
        for case in summary.get("cases", []):
            outcome = str(case.get("outcome", "error"))
            result.cases.append(TestCaseResult(name=str(case.get("name", "?")), outcome=outcome,
                                               message=truncate(str(case.get("message", "")), 1500),
                                               duration=float(case.get("duration", 0.0))))
        result.passed = sum(1 for c in result.cases if c.outcome == "passed")
        result.failed = sum(1 for c in result.cases if c.outcome == "failed")
        result.errors = sum(1 for c in result.cases if c.outcome == "error")
        if summary.get("collect_errors"):
            result.errors += len(summary["collect_errors"])
            result.error = "Test collection failed:\n" + truncate("\n".join(summary["collect_errors"]), 2000)
        return result
