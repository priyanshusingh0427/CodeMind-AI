"""Run the benchmark comparing the three approaches and save MEASURED results.

Run from the project folder (the one that contains app.py):
    python -m evaluation.benchmark_runner                    # eval split, all methods that can run
    python -m evaluation.benchmark_runner --methods static   # only Baseline 1
    python -m evaluation.benchmark_runner --limit 10 --split dev
    python -m evaluation.benchmark_runner --methods hybrid --resume   # continue an interrupted run
or from anywhere:
    python path/to/CodeMind-AI/run_benchmark.py --limit 10

Progress is saved after every example (evaluation/results/progress_*.jsonl), so an
interrupted run can be continued with --resume. Only a full run on the eval split
updates summary.json (shown in the app); trial runs write summary_trial.json.
Results of methods that are not re-run are kept when split, dataset and size match.

Methods
    static    Baseline 1 – AST + Pylint only (no repair)
    llm_only  Baseline 2 – one LLM call, no static context, no validation/repair
    hybrid    Proposed   – static + LLM + validation on *validation_tests* + up to N repairs

Scoring always uses each example's *heldout_tests*, which the repair loop never sees.
Repairs are scored by executing code ONLY inside the Docker sandbox; if it is
unavailable, repair metrics are recorded as not measured (null), never guessed.
Methods that need Ollama are skipped (and reported as skipped) when it is offline.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python evaluation/benchmark_runner.py` (or run_benchmark.py) from any working directory.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import argparse
import csv
import json
import re
import time
from datetime import datetime
from typing import Any, Optional

from config import BASE_DIR, DATASETS_DIR, EVAL_RESULTS_DIR, get_settings  # noqa: E402
from core.ai_debugger import AIDebugger, DebugResult  # noqa: E402
from core.llm_engine import OllamaClient  # noqa: E402
from core.sandbox import DockerSandbox  # noqa: E402
from core.test_generator import render_pytest  # noqa: E402
from core.test_validator import TestValidator  # noqa: E402
from evaluation.metrics import per_category, summarize_method  # noqa: E402
from utils.validators import Severity, TestCaseSpec  # noqa: E402

LAST_SUMMARY_PATH: Optional[Path] = None  # set by main(); used by run_benchmark.py for charts

SERIOUS = {Severity.CRITICAL, Severity.ERROR, Severity.WARNING}
SERIOUS_STATIC_CATEGORIES_EXCLUDED = {"style", "complexity"}


def resolve_dataset(dataset: Optional[Path]) -> Path:
    """Resolve a dataset path relative to the CWD first, then to the project folder."""
    if dataset is None:
        return DATASETS_DIR / "benchmark.json"
    if dataset.exists():
        return dataset
    candidate = BASE_DIR / dataset
    if candidate.exists():
        return candidate
    raise SystemExit(f"Dataset file not found: {dataset}")


def load_examples(split: str, limit: Optional[int], dataset: Optional[Path] = None) -> list[dict[str, Any]]:
    data = json.loads(resolve_dataset(dataset).read_text(encoding="utf-8"))
    examples = [e for e in data["examples"] if split == "all" or e["split"] == split]
    return examples[:limit] if limit else examples


def to_pytest(tests: list[dict[str, str]]) -> str:
    specs = [TestCaseSpec(name=f"case_{i}", call=t["call"], expected=t["expected"],
                          expects_exception=t["expects_exception"]) for i, t in enumerate(tests, 1)]
    return render_pytest(specs)[0]


def predicted_buggy(result: DebugResult) -> bool:
    """Did the method flag the program as buggy?"""
    static_flag = any(i.severity in SERIOUS and i.category.value not in SERIOUS_STATIC_CATEGORIES_EXCLUDED
                      for i in result.static_issues)
    ai_flag = any(i.severity in SERIOUS for i in result.ai_issues) or (result.llm_used and result.code_changed)
    return static_flag or ai_flag


def localized(result: DebugResult, bug_lines: list[int]) -> bool:
    targets = {line + offset for line in bug_lines for offset in (-1, 0, 1)}
    return any(i.line in targets and i.severity in SERIOUS for i in result.all_issues)


def evaluate_example(example: dict[str, Any], method: str, debugger: AIDebugger,
                     scorer: Optional[TestValidator]) -> dict[str, Any]:
    validation_code = to_pytest(example["validation_tests"]) if method == "hybrid" else ""
    started = time.perf_counter()
    on_buggy = debugger.debug(example["buggy_code"], example["intended_behavior"], validation_code, mode=method)
    seconds = time.perf_counter() - started
    on_clean = debugger.debug(example["fixed_code"], example["intended_behavior"], "", mode=method)

    repaired: Optional[bool] = None
    pass_rate: Optional[float] = None
    if method != "static" and scorer is not None:
        report = scorer.validate(on_buggy.corrected_code, to_pytest(example["heldout_tests"]))
        if report.status != "skipped":
            pass_rate = report.pass_rate
            repaired = report.status == "passed"
    cc_delta = mi_delta = None
    if on_buggy.metrics_after is not None and on_buggy.metrics_before.available and on_buggy.metrics_after.available:
        cc_delta = on_buggy.metrics_after.average_complexity - on_buggy.metrics_before.average_complexity
        mi_delta = on_buggy.metrics_after.maintainability_index - on_buggy.metrics_before.maintainability_index
    return {"id": example["id"], "category": example["category"], "difficulty": example["difficulty"],
            "method": method, "predicted_buggy_on_buggy": predicted_buggy(on_buggy),
            "predicted_buggy_on_clean": predicted_buggy(on_clean), "localized": localized(on_buggy,
                                                                                          example["bug_lines"]),
            "repair_status": on_buggy.repair_status, "attempts": on_buggy.attempts, "repaired": repaired,
            "heldout_pass_rate": pass_rate, "seconds": round(seconds, 3), "cc_delta": cc_delta,
            "mi_delta": mi_delta, "n_static_issues": len(on_buggy.static_issues),
            "n_ai_issues": len(on_buggy.ai_issues)}


def progress_file(split: str, dataset_name: str, method: str, model: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", f"{split}_{Path(dataset_name).stem}_{method}_{model or 'none'}")
    return EVAL_RESULTS_DIR / f"progress_{slug}.jsonl"


def load_progress(path: Path) -> dict[str, dict[str, Any]]:
    """Rows already evaluated in a previous (interrupted) run, keyed by example id."""
    done: dict[str, dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                done[row["id"]] = row
            except (json.JSONDecodeError, KeyError):
                continue  # a partially written last line is simply re-evaluated
    return done


def _fmt_seconds(seconds: float) -> str:
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m" if hours else f"{minutes}m{sec:02d}s"


def run_method(method: str, examples: list[dict[str, Any]], debugger: AIDebugger, scorer: Optional[TestValidator],
               checkpoint: Path, resume: bool) -> list[dict[str, Any]]:
    """Evaluate one method, appending each row to ``checkpoint`` as soon as it is measured."""
    done = load_progress(checkpoint) if resume else {}
    if not resume and checkpoint.exists():
        checkpoint.unlink()
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    measured_now = 0
    for index, example in enumerate(examples, 1):
        if example["id"] in done:
            rows.append(done[example["id"]])
            continue
        row = evaluate_example(example, method, debugger, scorer)
        rows.append(row)
        measured_now += 1
        with checkpoint.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
        elapsed = time.perf_counter() - started
        remaining = (len(examples) - index) * elapsed / measured_now
        print(f"[{method}] {index}/{len(examples)} {example['id']} status={row['repair_status']} "
              f"({row['seconds']:.1f}s, ETA {_fmt_seconds(remaining)})", file=sys.stderr, flush=True)
    if done:
        print(f"[{method}] reused {len(rows) - measured_now} row(s) from {checkpoint.name}", file=sys.stderr)
    return rows


def merge_previous(summary: dict[str, Any], previous_path: Path) -> None:
    """Keep measured methods from an earlier compatible run that were not re-run now."""
    if not previous_path.exists():
        return
    try:
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    old_meta, meta = previous.get("meta", {}), summary["meta"]
    if any(old_meta.get(k) != meta.get(k) for k in ("split", "n_examples")) or \
            Path(str(old_meta.get("dataset", "datasets/benchmark.json"))).name != Path(meta["dataset"]).name:
        return
    for method, values in previous.get("methods", {}).items():
        current = summary["methods"].get(method)
        if values.get("status") == "measured" and (current is None or current.get("status") != "measured"):
            summary["methods"][method] = values
            summary["per_category"][method] = previous.get("per_category", {}).get(method)
            summary["notes"].append(f"Results for '{method}' kept from the run at "
                                    f"{values.get('run_at', old_meta.get('timestamp', '?'))}.")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=["eval", "dev", "all", "external"], default="eval")
    parser.add_argument("--dataset", type=Path, default=None,
                        help="Alternative dataset file, e.g. datasets/external/quixbugs.json (use --split external)")
    parser.add_argument("--methods", default="static,llm_only,hybrid")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--model", default=None, help="Ollama model (default from settings / .env)")
    parser.add_argument("--no-pylint", action="store_true", help="AST checks only (faster)")
    parser.add_argument("--resume", action="store_true", help="Reuse rows saved by an interrupted run")
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.model:
        settings = settings.with_overrides(model_name=args.model)
    examples = load_examples(args.split, args.limit, args.dataset)
    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    unknown = [m for m in methods if m not in ("static", "llm_only", "hybrid")]
    if unknown:
        raise SystemExit(f"Unknown method(s): {', '.join(unknown)}")
    dataset_name = str(args.dataset or "datasets/benchmark.json")
    notes: list[str] = []

    llm = OllamaClient.from_settings(settings)
    llm_status = llm.check_status()
    sandbox = DockerSandbox(settings)
    sandbox_status = sandbox.status()
    scorer = TestValidator(sandbox) if sandbox_status.available else None
    print(f"Examples: {len(examples)} ({args.split}) | LLM: {llm_status.message} | Sandbox: {sandbox_status.message}",
          file=sys.stderr)
    if not sandbox_status.available:
        notes.append(f"Sandbox unavailable ({sandbox_status.message}); repair metrics were NOT measured.")

    EVAL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    summary_methods: dict[str, Any] = {}
    for method in methods:
        if method in ("llm_only", "hybrid") and not llm_status.available:
            notes.append(f"Method '{method}' skipped: {llm_status.message}")
            summary_methods[method] = {"status": "not_run", "reason": llm_status.message}
            continue
        model = settings.model_name if method != "static" else ""
        debugger = AIDebugger(settings, llm=llm if method != "static" else None,
                              validator=TestValidator(sandbox) if (method == "hybrid" and scorer) else None,
                              use_pylint=not args.no_pylint)
        checkpoint = progress_file(args.split, dataset_name, method, model)
        rows = run_method(method, examples, debugger, scorer, checkpoint, args.resume)
        all_rows.extend(rows)
        summary_methods[method] = {"status": "measured", "run_at": datetime.now().isoformat(timespec="seconds"),
                                   "model": model or None, "sandbox_scoring": scorer is not None,
                                   **summarize_method(rows), "per_category": per_category(rows)}
        if method == "static":
            summary_methods[method]["repair_rate"] = None
            notes.append("Static baseline performs no repair, so repair metrics are not applicable (null).")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    meta = {"timestamp": datetime.now().isoformat(timespec="seconds"), "split": args.split,
            "dataset": dataset_name, "n_examples": len(examples), "methods": methods,
            "model": settings.model_name if llm_status.available else None,
            "max_repair_attempts": settings.max_repair_attempts, "temperature": settings.temperature,
            "pylint": not args.no_pylint, "sandbox": sandbox_status.available,
            "python": sys.version.split()[0], "platform": sys.platform}
    summary = {"meta": meta, "methods": {m: {k: v for k, v in s.items() if k != "per_category"}
                                         for m, s in summary_methods.items()},
               "per_category": {m: s.get("per_category") for m, s in summary_methods.items()}, "notes": notes}
    # Only a full run on the default eval split updates the main results shown in the app;
    # trial runs (--limit, other splits/datasets) go to summary_trial.json.
    is_main = args.split == "eval" and args.dataset is None and args.limit is None
    summary_path = EVAL_RESULTS_DIR / ("summary.json" if is_main else "summary_trial.json")
    meta["kind"] = "main" if is_main else "trial"
    global LAST_SUMMARY_PATH  # pylint: disable=global-statement
    LAST_SUMMARY_PATH = summary_path
    merge_previous(summary, summary_path)

    details_path = EVAL_RESULTS_DIR / f"details_{stamp}.csv"
    if all_rows:
        with details_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(all_rows[0]))
            writer.writeheader()
            writer.writerows(all_rows)
    summary_json = json.dumps(summary, indent=2)
    (EVAL_RESULTS_DIR / f"summary_{stamp}.json").write_text(summary_json, encoding="utf-8")
    summary_path.write_text(summary_json, encoding="utf-8")
    with summary_path.with_suffix(".csv").open("w", newline="", encoding="utf-8") as handle:
        keys = sorted({k for s in summary["methods"].values() for k in s})
        writer = csv.DictWriter(handle, fieldnames=["method", *keys])
        writer.writeheader()
        for method, values in summary["methods"].items():
            writer.writerow({"method": method, **values})
    print(summary_json)
    print(f"\nSaved: {details_path if all_rows else '(no rows)'}, {summary_path}", file=sys.stderr)
    if not is_main:
        print("This was a trial run (limit/split/dataset), so the main results in summary.json were not changed.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
