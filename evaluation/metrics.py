"""Evaluation metrics (computed only from measured per-example results)."""

from __future__ import annotations

from statistics import mean
from typing import Any, Optional

from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score


def detection_metrics(y_true: list[int], y_pred: list[int]) -> dict[str, Optional[float]]:
    """Binary 'is this program buggy?' metrics. 1 = buggy, 0 = clean."""
    if not y_true:
        return {"accuracy": None, "precision": None, "recall": None, "f1": None, "false_positive_rate": None}
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "false_positive_rate": round(float(fp / (fp + tn)), 4) if (fp + tn) else None,
        "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
    }


def _avg(values: list[Optional[float]]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    return round(mean(clean), 4) if clean else None


def summarize_method(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-example rows of one method into a summary dict.

    Each row contains: predicted_buggy_on_buggy, predicted_buggy_on_clean, localized,
    repaired (bool or None when not measured), heldout_pass_rate (float or None),
    seconds, cc_delta, mi_delta.
    """
    y_true = [1] * len(rows) + [0] * len(rows)
    y_pred = [int(r["predicted_buggy_on_buggy"]) for r in rows] + [int(r["predicted_buggy_on_clean"]) for r in rows]
    summary: dict[str, Any] = {"n_examples": len(rows)}
    summary.update(detection_metrics(y_true, y_pred))
    summary["localization_accuracy"] = _avg([1.0 if r["localized"] else 0.0 for r in rows])
    repaired = [r["repaired"] for r in rows if r["repaired"] is not None]
    summary["repair_rate"] = round(sum(repaired) / len(repaired), 4) if repaired else None
    summary["test_pass_rate"] = _avg([r["heldout_pass_rate"] for r in rows])
    summary["avg_response_time_s"] = _avg([r["seconds"] for r in rows])
    summary["avg_cc_change"] = _avg([r["cc_delta"] for r in rows])
    summary["avg_mi_change"] = _avg([r["mi_delta"] for r in rows])
    return summary


def per_category(rows: list[dict[str, Any]]) -> dict[str, dict[str, Optional[float]]]:
    """Recall and repair rate per bug category."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row["category"], []).append(row)
    result = {}
    for category, items in sorted(groups.items()):
        repaired = [r["repaired"] for r in items if r["repaired"] is not None]
        result[category] = {"n": len(items),
                            "recall": round(sum(r["predicted_buggy_on_buggy"] for r in items) / len(items), 4),
                            "repair_rate": round(sum(repaired) / len(repaired), 4) if repaired else None}
    return result
