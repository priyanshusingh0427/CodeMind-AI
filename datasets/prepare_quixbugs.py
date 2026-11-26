"""Download QuixBugs (MIT licence) and convert its Python programs to the CodeMind AI format.

QuixBugs: Lin et al., "QuixBugs: A Multi-Lingual Program Repair Benchmark Set Based on the Quixey
Challenge", SPLASH Companion 2017. Repository: https://github.com/jkoppel/QuixBugs (MIT licence).

    python -m datasets.prepare_quixbugs            # writes datasets/external/quixbugs.json

Only programs that have JSON test cases are converted (graph programs that need
custom Python test fixtures are skipped). All QuixBugs examples are marked
``split='external'`` so they never mix with the custom dev/eval splits.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import requests

URL = "https://github.com/jkoppel/QuixBugs/archive/refs/heads/master.zip"
OUT = Path(__file__).parent / "external" / "quixbugs.json"
MAX_TESTS = 6


def _strip_header(code: str) -> str:
    """Correct programs start with a 'def' after comments; keep the code only."""
    return code.replace("\r\n", "\n").strip("\n") + "\n"


def convert(archive: zipfile.ZipFile) -> list[dict]:
    names = archive.namelist()
    root = names[0].split("/")[0]
    examples = []
    for path in sorted(n for n in names if n.startswith(f"{root}/json_testcases/") and n.endswith(".json")):
        program = Path(path).stem
        buggy_path = f"{root}/python_programs/{program}.py"
        fixed_path = f"{root}/correct_python_programs/{program}.py"
        if buggy_path not in names or fixed_path not in names:
            continue
        tests = []
        for line in archive.read(path).decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                args, expected = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            args = args if isinstance(args, list) else [args]
            call = f"{program}({', '.join(repr(a) for a in args)})"
            tests.append({"call": call, "expected": repr(expected), "expects_exception": ""})
            if len(tests) >= MAX_TESTS:
                break
        if not tests:
            continue
        half = max(1, len(tests) // 2)
        examples.append({
            "id": f"QB-{program}", "split": "external", "category": "logical_error", "difficulty": "hard",
            "intended_behavior": f"QuixBugs program '{program}' (see the QuixBugs repository for the specification).",
            "buggy_code": _strip_header(archive.read(buggy_path).decode("utf-8")),
            "fixed_code": _strip_header(archive.read(fixed_path).decode("utf-8")),
            "entry_point": program, "bug_lines": [], "validation_tests": tests[:half],
            "heldout_tests": tests[half:] or tests[:1], "expected_output": tests[0]["expected"],
            "error_explanation": "One-line bug from QuixBugs; bug line not annotated in this conversion.",
            "source": "QuixBugs (MIT licence), https://github.com/jkoppel/QuixBugs",
        })
    return examples


def main() -> None:
    print(f"Downloading {URL} …")
    response = requests.get(URL, timeout=60)
    response.raise_for_status()
    examples = convert(zipfile.ZipFile(io.BytesIO(response.content)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"name": "QuixBugs (Python subset with JSON tests)", "license": "MIT",
                               "source": URL, "note": "Expected values come from the QuixBugs JSON test cases. "
                                                     "Some generators/float outputs may need manual review.",
                               "examples": examples}, indent=2), encoding="utf-8")
    print(f"Wrote {len(examples)} QuixBugs examples to {OUT}")


if __name__ == "__main__":
    main()
