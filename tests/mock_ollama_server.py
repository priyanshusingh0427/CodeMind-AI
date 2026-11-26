"""A tiny fake Ollama server for UI demos and integration tests WITHOUT a real model.

It implements ``GET /api/tags`` and ``POST /api/chat`` and returns *canned*,
rule-based answers (a few string replacements for the bundled sample bugs).
It is NOT an AI model and must never be used to produce evaluation results.

Usage:
    python tests/mock_ollama_server.py --port 11435
    # then set OLLAMA_HOST=http://localhost:11435 and OLLAMA_MODEL=mock-coder
"""

from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "mock-coder"
CANNED_FIXES = [
    ("totl", "total", "NameError: 'totl' is a typo for 'total'"),
    ("range(1, n)", "range(1, n + 1)", "Off-by-one: range excludes the end value"),
    ("def is_even(n)\n", "def is_even(n):\n", "Missing colon after function signature"),
    ("while low < high:", "while low <= high:", "Loop stops before checking the last candidate"),
]


def _extract_code(prompt: str) -> str:
    match = re.search(r"<<<UNTRUSTED_CODE_START>>>\n(.*?)\n<<<UNTRUSTED_CODE_END>>>", prompt, flags=re.DOTALL)
    if not match:
        return ""
    lines = match.group(1).splitlines()
    return "\n".join(re.sub(r"^\s*\d+\| ?", "", line, count=1) for line in lines) + "\n"


def _debug_answer(prompt: str) -> dict:
    code = _extract_code(prompt)
    findings, changes, fixed = [], [], code
    for old, new, why in CANNED_FIXES:
        if old in fixed:
            line = fixed[: fixed.index(old)].count("\n") + 1
            fixed = fixed.replace(old, new)
            findings.append({"error_type": "bug", "line_number": line, "severity": "error", "description": why,
                             "suggested_correction": f"Replace `{old.strip()}` with `{new.strip()}`"})
            changes.append(f"Line {line}: {why}")
    return {"findings": findings, "corrected_code": fixed, "changes": changes,
            "optimization_suggestions": [], "explanation": "Canned answer from the mock server (not a real model).",
            "assumptions": ["Mock server: rule-based replacements only."], "no_bugs_found": not findings}


def _tests_answer(prompt: str) -> dict:
    code = _extract_code(prompt)
    match = re.search(r"^def (\w+)\(", code, flags=re.MULTILINE)
    name = match.group(1) if match else "f"
    return {"tests": [{"name": f"test_{name}_smoke", "category": "normal", "call": f"callable({name})",
                       "expected": "True", "expects_exception": "", "description": "mock smoke test"}]}


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/tags":
            self._send({"models": [{"name": MODEL}]})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        request = json.loads(self.rfile.read(length) or b"{}")
        prompt = "\n".join(m.get("content", "") for m in request.get("messages", []))
        last = request.get("messages", [{}])[-1].get("content", "")
        if request.get("format") == "json":
            if "Write " in last and "test cases" in last:
                content = json.dumps(_tests_answer(last))
            elif "Suggest optimisations" in last:
                content = json.dumps({"suggestions": ["(mock) Consider built-ins."],
                                      "estimated_time_complexity": "unknown", "estimated_space_complexity": "unknown",
                                      "optimized_code": "", "explanation": "Mock server answer."})
            else:
                content = json.dumps(_debug_answer(last if "UNTRUSTED_CODE_START" in last else prompt))
        else:
            content = "This is a canned reply from the **mock Ollama server**. Start a real model for answers."
        self._send({"model": MODEL, "message": {"role": "assistant", "content": content}, "done": True})

    def log_message(self, *_args) -> None:  # keep test output quiet
        return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=11435)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Mock Ollama listening on http://127.0.0.1:{args.port} (model '{MODEL}')")
    server.serve_forever()


if __name__ == "__main__":
    main()
