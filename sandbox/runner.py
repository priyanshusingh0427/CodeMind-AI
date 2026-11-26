"""Test runner executed *inside* the sandbox container.

It runs pytest on ``test_solution.py`` and prints a JSON summary between
markers so the host can parse it even if the code under test prints output.
This file is copied into a temporary read-only directory for each run.
"""

import json
import sys

MARKER = "@@CODEMIND_RESULT@@"


class _Collector:
    def __init__(self):
        self.cases = []
        self.collect_errors = []

    def pytest_runtest_logreport(self, report):
        if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
            message = ""
            if report.outcome != "passed":
                message = str(report.longrepr)[-1500:]
            outcome = "error" if report.when == "setup" else report.outcome
            self.cases.append({"name": report.nodeid.split("::")[-1], "outcome": outcome,
                               "message": message, "duration": round(report.duration, 4)})

    def pytest_collectreport(self, report):
        if report.outcome == "failed":
            self.collect_errors.append(str(report.longrepr)[-2000:])


def main():
    sys.path.insert(0, "/work")
    try:
        import pytest
    except ImportError:
        print(MARKER + json.dumps({"fatal": "pytest is not installed in the sandbox image"}) + MARKER)
        return 3
    collector = _Collector()
    exit_code = pytest.main(["-q", "-p", "no:cacheprovider", "--no-header", "-rN", "/work/test_solution.py"],
                            plugins=[collector])
    summary = {"exit_code": int(exit_code), "cases": collector.cases, "collect_errors": collector.collect_errors}
    print(MARKER + json.dumps(summary) + MARKER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
