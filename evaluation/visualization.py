"""Create comparison charts from MEASURED benchmark results (evaluation/results/summary.json).

    python -m evaluation.visualization            # main results (summary.json)
    python -m evaluation.visualization --trial    # trial runs (summary_trial.json), files prefixed trial_

Writes interactive Plotly HTML files to evaluation/results/. Nothing is drawn for
methods that were not run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:  # allow running this file from any working directory
    sys.path.insert(0, str(_ROOT))

import plotly.graph_objects as go  # noqa: E402

from config import EVAL_RESULTS_DIR  # noqa: E402

METRICS = ["accuracy", "precision", "recall", "f1", "false_positive_rate", "localization_accuracy", "repair_rate",
           "test_pass_rate"]


def main(argv: list[str] | None = None) -> int:
    trial = "--trial" in (sys.argv[1:] if argv is None else argv)
    path = EVAL_RESULTS_DIR / ("summary_trial.json" if trial else "summary.json")
    prefix = "trial_" if trial else ""
    if not path.exists():
        print(f"No {path.name} found. Run `python -m evaluation.benchmark_runner` first.", file=sys.stderr)
        return 1
    summary = json.loads(path.read_text(encoding="utf-8"))
    measured = {m: s for m, s in summary["methods"].items() if s.get("status") == "measured"}
    if not measured:
        print("No measured methods in summary.json.", file=sys.stderr)
        return 1
    fig = go.Figure()
    for method, values in measured.items():
        fig.add_bar(name=method, x=METRICS, y=[values.get(m) for m in METRICS])
    fig.update_layout(barmode="group", title=f"Benchmark comparison ({summary['meta']['split']} split, "
                                             f"n={summary['meta']['n_examples']})", yaxis_range=[0, 1],
                      template="plotly_white")
    out1 = EVAL_RESULTS_DIR / f"{prefix}comparison_metrics.html"
    fig.write_html(out1, include_plotlyjs="cdn")

    timing = go.Figure(go.Bar(x=list(measured), y=[v.get("avg_response_time_s") for v in measured.values()]))
    timing.update_layout(title="Average response time per buggy program (s)", template="plotly_white")
    out2 = EVAL_RESULTS_DIR / f"{prefix}comparison_time.html"
    timing.write_html(out2, include_plotlyjs="cdn")

    per_cat = summary.get("per_category", {})
    cat_fig = go.Figure()
    for method, cats in per_cat.items():
        if cats:
            cat_fig.add_bar(name=method, x=list(cats), y=[c["recall"] for c in cats.values()])
    cat_fig.update_layout(barmode="group", title="Detection recall by bug category", template="plotly_white",
                          yaxis_range=[0, 1])
    out3 = EVAL_RESULTS_DIR / f"{prefix}recall_by_category.html"
    cat_fig.write_html(out3, include_plotlyjs="cdn")
    print(f"Wrote {out1}, {out2}, {out3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
