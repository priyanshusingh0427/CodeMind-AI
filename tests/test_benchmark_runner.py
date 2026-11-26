"""Tests for the benchmark runner's robustness features (checkpoints, resume, trial runs)."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from config import BASE_DIR
from evaluation import benchmark_runner as br


class _NoSandbox:
    def __init__(self, *_args, **_kwargs):
        pass

    def status(self):
        return SimpleNamespace(available=False, message="disabled in test")


class _NoLLM:
    @classmethod
    def from_settings(cls, _settings):
        return cls()

    def check_status(self):
        return SimpleNamespace(available=False, message="no LLM in test", models=[])


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(br, "EVAL_RESULTS_DIR", tmp_path)
    monkeypatch.setattr(br, "DockerSandbox", _NoSandbox)
    monkeypatch.setattr(br, "OllamaClient", _NoLLM)
    return tmp_path


def test_resolve_dataset(tmp_path, monkeypatch):
    assert br.resolve_dataset(None) == BASE_DIR / "datasets" / "benchmark.json"
    monkeypatch.chdir(tmp_path)  # a relative path still resolves against the project folder
    assert br.resolve_dataset(Path("datasets/benchmark.json")) == BASE_DIR / "datasets" / "benchmark.json"
    with pytest.raises(SystemExit):
        br.resolve_dataset(Path("does/not/exist.json"))


def test_load_progress_ignores_broken_last_line(tmp_path):
    path = tmp_path / "progress.jsonl"
    path.write_text(json.dumps({"id": "A", "x": 1}) + "\n" + '{"id": "B", "x"', encoding="utf-8")
    assert list(br.load_progress(path)) == ["A"]


def test_trial_run_does_not_touch_main_summary_and_resume_reuses_rows(isolated, capsys):
    main_summary = isolated / "summary.json"
    main_summary.write_text('{"sentinel": true}', encoding="utf-8")
    args = ["--split", "dev", "--limit", "2", "--methods", "static,hybrid", "--no-pylint"]
    assert br.main(args) == 0
    assert json.loads(main_summary.read_text(encoding="utf-8")) == {"sentinel": True}
    trial = json.loads((isolated / "summary_trial.json").read_text(encoding="utf-8"))
    assert trial["meta"]["kind"] == "trial" and trial["meta"]["n_examples"] == 2
    assert trial["methods"]["static"]["status"] == "measured"
    assert trial["methods"]["hybrid"]["status"] == "not_run"
    checkpoint = br.progress_file("dev", "datasets/benchmark.json", "static", "")
    assert len(checkpoint.read_text(encoding="utf-8").splitlines()) == 2

    capsys.readouterr()
    assert br.main(args + ["--resume"]) == 0
    assert "reused 2 row(s)" in capsys.readouterr().err


def test_unknown_method_rejected(isolated):
    with pytest.raises(SystemExit):
        br.main(["--methods", "static,magic", "--limit", "1"])


def test_merge_previous_keeps_measured_methods(tmp_path):
    previous = {"meta": {"split": "eval", "n_examples": 92, "dataset": "datasets/benchmark.json"},
                "methods": {"static": {"status": "measured", "recall": 0.38, "run_at": "2026-11-25T18:33:50"}},
                "per_category": {"static": {"x": {}}}}
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(previous), encoding="utf-8")
    summary = {"meta": {"split": "eval", "n_examples": 92, "dataset": "datasets/benchmark.json"},
               "methods": {"hybrid": {"status": "measured"}}, "per_category": {"hybrid": None}, "notes": []}
    br.merge_previous(summary, path)
    assert summary["methods"]["static"]["recall"] == 0.38 and summary["notes"]
    other = {**summary, "meta": {**summary["meta"], "n_examples": 10}, "methods": {}, "notes": []}
    br.merge_previous(other, path)
    assert "static" not in other["methods"]


def test_scripts_run_from_another_folder(tmp_path):
    """Regression test for 'ModuleNotFoundError: No module named evaluation' when run from the wrong folder."""
    for script in ("run_benchmark.py", "check_setup.py"):
        proc = subprocess.run([sys.executable, str(BASE_DIR / script), "--help"], cwd=tmp_path,
                              capture_output=True, text=True, timeout=120, check=False)
        assert proc.returncode == 0, proc.stderr
    proc = subprocess.run([sys.executable, str(BASE_DIR / "evaluation" / "benchmark_runner.py"), "--help"],
                          cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    assert proc.returncode == 0, proc.stderr
