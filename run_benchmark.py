"""Run the CodeMind AI benchmark from any folder.

    python run_benchmark.py --limit 10
    python C:\\path\\to\\CodeMind-AI\\run_benchmark.py --methods hybrid --resume

Same options as ``python -m evaluation.benchmark_runner`` (see --help). After it finishes,
charts are regenerated with ``evaluation.visualization`` unless --no-charts is given.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation import benchmark_runner, visualization  # noqa: E402  # pylint: disable=wrong-import-position


def main() -> int:
    argv = sys.argv[1:]
    charts = "--no-charts" not in argv
    argv = [a for a in argv if a != "--no-charts"]
    code = benchmark_runner.main(argv)
    if code == 0 and charts and benchmark_runner.LAST_SUMMARY_PATH is not None:
        trial = benchmark_runner.LAST_SUMMARY_PATH.name == "summary_trial.json"
        visualization.main(["--trial"] if trial else [])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
