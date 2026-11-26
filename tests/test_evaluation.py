"""Tests for the dataset file and evaluation metrics."""

import json

from config import DATASETS_DIR
from evaluation.benchmark_runner import load_examples, to_pytest
from evaluation.metrics import detection_metrics, per_category, summarize_method

REQUIRED = {"id", "split", "category", "difficulty", "intended_behavior", "buggy_code", "fixed_code", "bug_lines",
            "validation_tests", "heldout_tests", "expected_output", "error_explanation"}


def test_dataset_integrity():
    data = json.loads((DATASETS_DIR / "benchmark.json").read_text(encoding="utf-8"))
    examples = data["examples"]
    assert len(examples) >= 100
    assert len({e["id"] for e in examples}) == len(examples)
    for example in examples:
        assert REQUIRED <= set(example), example["id"]
        assert example["split"] in {"dev", "eval"}
        assert example["validation_tests"] and example["heldout_tests"]
        visible = {t["call"] for t in example["validation_tests"]}
        assert not visible & {t["call"] for t in example["heldout_tests"]}, "held-out tests must be unseen"
        assert example["buggy_code"] != example["fixed_code"]
        compile(example["fixed_code"], example["id"], "exec")
        compile(to_pytest(example["heldout_tests"]), "t", "exec")
    assert len(load_examples("dev", None)) + len(load_examples("eval", None)) == len(examples)
    dev_ids = {e["id"] for e in load_examples("dev", None)}
    assert not dev_ids & {e["id"] for e in load_examples("eval", None)}


def test_detection_metrics():
    m = detection_metrics([1, 1, 0, 0], [1, 0, 0, 1])
    assert m["precision"] == 0.5 and m["recall"] == 0.5 and m["false_positive_rate"] == 0.5
    assert detection_metrics([], [])["f1"] is None


def test_summarize_method_handles_unmeasured_repairs():
    rows = [{"id": "a", "category": "x", "predicted_buggy_on_buggy": True, "predicted_buggy_on_clean": False,
             "localized": True, "repaired": None, "heldout_pass_rate": None, "seconds": 1.0, "cc_delta": None,
             "mi_delta": None},
            {"id": "b", "category": "y", "predicted_buggy_on_buggy": False, "predicted_buggy_on_clean": False,
             "localized": False, "repaired": True, "heldout_pass_rate": 1.0, "seconds": 3.0, "cc_delta": 0.0,
             "mi_delta": -1.0}]
    summary = summarize_method(rows)
    assert summary["recall"] == 0.5 and summary["precision"] == 1.0
    assert summary["repair_rate"] == 1.0 and summary["avg_response_time_s"] == 2.0
    assert per_category(rows)["x"]["repair_rate"] is None
