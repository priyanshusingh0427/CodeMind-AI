"""CodeMind AI – installation and integration self-check.

Run it from anywhere:

    python check_setup.py                  # full check incl. one real LLM call
    python check_setup.py --skip-llm       # skip the (slow) model call
    python check_setup.py --build-sandbox  # also build the Docker sandbox image if missing

It checks Python, packages, the database, Ollama (connection, model, one real
structured debugging call on a sample bug), Docker and the sandbox, and writes a
summary to data/setup_check.json. Output is plain ASCII so it works in any
Windows console.
"""

from __future__ import annotations

# Project modules are imported inside the checks on purpose, so a missing package is reported, not a crash.
# pylint: disable=import-outside-toplevel

import argparse
import importlib
import json
import platform
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PACKAGES = ["streamlit", "streamlit_ace", "requests", "pydantic", "pylint", "radon", "pytest", "sqlalchemy", "plotly",
            "pandas", "numpy", "sklearn", "reportlab", "dotenv"]
SAMPLE_CODE = ("def average(numbers):\n    total = 0\n    for n in numbers:\n        total += n\n"
               "    return totl / len(numbers)\n")
SAMPLE_TESTS = ("from solution import average\n\n\ndef test_average():\n    assert average([1, 2, 3]) == 2\n\n\n"
                "def test_single():\n    assert average([5]) == 5\n")

results: list[dict[str, Any]] = []


def report(status: str, name: str, detail: str = "") -> None:
    results.append({"check": name, "status": status, "detail": detail})
    print(f"[{status:<4}] {name}" + (f" - {detail}" if detail else ""), flush=True)


def check_python() -> None:
    version = sys.version_info
    ok = version >= (3, 11)
    report("OK" if ok else "FAIL", "Python version", f"{platform.python_version()} ({sys.executable})"
           + ("" if ok else " - Python 3.11 or newer is required"))
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    report("OK" if in_venv else "WARN", "Virtual environment", "active" if in_venv else
           "not active - activate .venv before installing/running (see docs/installation.md)")
    report("OK", "Project folder", str(ROOT))
    nested = ROOT.parent / "CodeMind-AI" / "app.py"
    if ROOT.name == "CodeMind-AI" and ROOT.parent.name == "CodeMind-AI" and nested.exists():
        report("WARN", "Folder layout", "the project is inside a second 'CodeMind-AI' folder (common after 'Extract "
                                       "All' on Windows). Always `cd` into the folder that contains app.py.")


def check_packages() -> bool:
    missing = []
    for name in PACKAGES:
        try:
            module = importlib.import_module(name)
            version = getattr(module, "__version__", "")
            report("OK", f"package {name}", str(version))
        except ImportError:
            missing.append(name)
            report("FAIL", f"package {name}", "missing - run `pip install -r requirements.txt` in the venv")
    return not missing


def check_database() -> None:
    from config import get_settings
    from core.ai_debugger import AIDebugger
    from database.operations import get_session, save_session

    with tempfile.TemporaryDirectory() as tmp:
        settings = get_settings().with_overrides(database_url=f"sqlite:///{(Path(tmp) / 'check.db').as_posix()}")
        payload = AIDebugger(settings, use_pylint=False).debug(SAMPLE_CODE).to_dict()
        session_id = save_session(settings.database_url, payload)
        ok = get_session(settings.database_url, session_id) is not None
        from database.connection import get_engine
        get_engine(settings.database_url).dispose()  # release the file so Windows can delete the temp folder
    report("OK" if ok else "FAIL", "SQLite history", "write + read OK" if ok else "could not read back the session")


def check_static() -> None:
    from core.static_analyzer import analyze_static

    started = time.perf_counter()
    static = analyze_static(SAMPLE_CODE)
    found = any("totl" in i.message for i in static.issues)
    detail = f"{len(static.issues)} issue(s) in {time.perf_counter() - started:.1f}s"
    if static.pylint_error:
        report("WARN", "Static analysis (AST + Pylint)", f"{detail}; Pylint: {static.pylint_error}")
    else:
        report("OK" if found else "FAIL", "Static analysis (AST + Pylint)", detail)


def check_ollama(skip_llm: bool) -> Any:
    from config import get_settings
    from core.llm_engine import OllamaClient

    settings = get_settings()
    client = OllamaClient.from_settings(settings)
    status = client.check_status()
    if not status.models and not status.available:
        report("FAIL", "Ollama server", status.message)
        return None
    report("OK", "Ollama server", f"{settings.ollama_host} - models: {', '.join(status.models) or 'none'}")
    if not status.available:
        report("FAIL", "Ollama model", status.message)
        return None
    report("OK", "Ollama model", settings.model_name)
    if skip_llm:
        report("SKIP", "LLM debugging call", "--skip-llm given")
        return client

    from core.ai_debugger import AIDebugger

    print("       Asking the model to fix a sample bug (can take 10-120 s on CPU)...", flush=True)
    result = AIDebugger(settings, llm=client).debug(SAMPLE_CODE, "Return the average of a list of numbers.")
    fixed = "totl" not in result.corrected_code and "total" in result.corrected_code
    detail = (f"status={result.repair_status}, attempts={result.attempts}, {result.duration:.1f}s, "
              f"AI findings={len(result.ai_issues)}, typo fixed={'yes' if fixed else 'no'}")
    if result.repair_status == "llm_failed":
        report("FAIL", "LLM debugging call", f"{result.llm_message}")
    else:
        report("OK" if fixed else "WARN", "LLM debugging call", detail)
    return client


def check_docker(build: bool, client: Any) -> None:
    from config import get_settings
    from core.sandbox import DockerSandbox
    from core.test_validator import TestValidator

    settings = get_settings()
    sandbox = DockerSandbox(settings)
    status = sandbox.status()
    if not status.docker_installed:
        report("WARN", "Docker", f"{status.message} The app works, but never executes code (static-only mode).")
        return
    if not status.daemon_running:
        report("WARN", "Docker", status.message)
        return
    if not status.image_present and build:
        print("       Building the sandbox image (first time downloads python:3.11-slim)...", flush=True)
        ok, output = sandbox.build_image()
        report("OK" if ok else "FAIL", "Sandbox image build", "" if ok else output[-500:])
        status = sandbox.status()
    if not status.available:
        report("WARN", "Sandbox", status.message)
        return
    report("OK", "Sandbox image", settings.sandbox_image)
    fixed = SAMPLE_CODE.replace("totl", "total")
    good = TestValidator(sandbox).validate(fixed, SAMPLE_TESTS)
    bad = TestValidator(sandbox).validate(SAMPLE_CODE, SAMPLE_TESTS)
    ok = good.status == "passed" and bad.status in ("failed", "error")
    report("OK" if ok else "FAIL", "Sandboxed test run", f"fixed code: {good.status} ({good.duration:.1f}s), "
                                                         f"buggy code: {bad.status}")
    if client is not None and ok:
        from core.ai_debugger import AIDebugger

        print("       Running the full hybrid pipeline with sandbox verification...", flush=True)
        result = AIDebugger(settings, llm=client, validator=TestValidator(sandbox)).debug(
            SAMPLE_CODE, "Return the average of a list of numbers.", SAMPLE_TESTS)
        report("OK" if result.repair_status == "verified" else "WARN", "Hybrid pipeline + sandbox",
               f"status={result.repair_status}, attempts={result.attempts}, {result.duration:.1f}s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-llm", action="store_true", help="do not send a request to the model")
    parser.add_argument("--build-sandbox", action="store_true", help="build the Docker sandbox image if missing")
    args = parser.parse_args()

    print("CodeMind AI setup check\n", flush=True)
    check_python()
    if not check_packages():
        print("\nInstall the missing packages first.")
        return 1
    check_database()
    check_static()
    client = check_ollama(args.skip_llm)
    check_docker(args.build_sandbox, client if not args.skip_llm else None)

    from config import DATA_DIR

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / "setup_check.json"
    out.write_text(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "platform": platform.platform(),
                               "python": platform.python_version(), "results": results}, indent=2), encoding="utf-8")
    failures = sum(r["status"] == "FAIL" for r in results)
    warnings = sum(r["status"] == "WARN" for r in results)
    print(f"\n{failures} failure(s), {warnings} warning(s). Details saved to {out}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
