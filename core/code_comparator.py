"""Line-level comparison of original and corrected code using :mod:`difflib`."""

from __future__ import annotations

import difflib
import html
from dataclasses import dataclass, field


@dataclass
class DiffRow:
    """One row of a side-by-side diff."""

    kind: str  # equal | added | removed | modified
    left_no: int | None
    left: str
    right_no: int | None
    right: str


@dataclass
class DiffResult:
    rows: list[DiffRow] = field(default_factory=list)
    added: int = 0
    removed: int = 0
    modified: int = 0
    similarity: float = 1.0
    unified: str = ""

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.modified)


def compare_code(original: str, corrected: str) -> DiffResult:
    """Compute a side-by-side diff with added / removed / modified counts."""
    left = original.splitlines()
    right = corrected.splitlines()
    matcher = difflib.SequenceMatcher(a=left, b=right, autojunk=False)
    result = DiffResult(similarity=round(matcher.ratio(), 4))
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                result.rows.append(DiffRow("equal", i1 + offset + 1, left[i1 + offset], j1 + offset + 1,
                                           right[j1 + offset]))
        elif tag == "delete":
            for i in range(i1, i2):
                result.rows.append(DiffRow("removed", i + 1, left[i], None, ""))
                result.removed += 1
        elif tag == "insert":
            for j in range(j1, j2):
                result.rows.append(DiffRow("added", None, "", j + 1, right[j]))
                result.added += 1
        else:  # replace: pair lines as modifications, overflow as add/remove
            pairs = min(i2 - i1, j2 - j1)
            for k in range(pairs):
                result.rows.append(DiffRow("modified", i1 + k + 1, left[i1 + k], j1 + k + 1, right[j1 + k]))
                result.modified += 1
            for i in range(i1 + pairs, i2):
                result.rows.append(DiffRow("removed", i + 1, left[i], None, ""))
                result.removed += 1
            for j in range(j1 + pairs, j2):
                result.rows.append(DiffRow("added", None, "", j + 1, right[j]))
                result.added += 1
    result.unified = "".join(difflib.unified_diff([line + "\n" for line in left], [line + "\n" for line in right],
                                                  fromfile="original.py", tofile="corrected.py"))
    return result


def _inline_highlight(old: str, new: str) -> tuple[str, str]:
    """Highlight changed characters within a modified line pair."""
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    left_parts, right_parts = [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        a, b = html.escape(old[i1:i2]), html.escape(new[j1:j2])
        if tag == "equal":
            left_parts.append(a)
            right_parts.append(b)
        else:
            if a:
                left_parts.append(f'<span class="cm-del-chr">{a}</span>')
            if b:
                right_parts.append(f'<span class="cm-add-chr">{b}</span>')
    return "".join(left_parts), "".join(right_parts)


def render_side_by_side_html(diff: DiffResult) -> str:
    """Return an HTML table (styled by assets/style.css classes) for the diff."""
    css_left = {"equal": "", "removed": "cm-del", "modified": "cm-del", "added": "cm-empty"}
    css_right = {"equal": "", "added": "cm-add", "modified": "cm-add", "removed": "cm-empty"}
    marks = {"equal": ("", ""), "removed": ("-", ""), "added": ("", "+"), "modified": ("~", "~")}
    body = []
    for row in diff.rows:
        if row.kind == "modified":
            left_html, right_html = _inline_highlight(row.left, row.right)
        else:
            left_html, right_html = html.escape(row.left), html.escape(row.right)
        lm, rm = marks[row.kind]
        body.append(
            "<tr>"
            f'<td class="cm-ln">{row.left_no or ""}</td><td class="cm-mark">{lm}</td>'
            f'<td class="cm-code {css_left[row.kind]}">{left_html or "&nbsp;"}</td>'
            f'<td class="cm-ln">{row.right_no or ""}</td><td class="cm-mark">{rm}</td>'
            f'<td class="cm-code {css_right[row.kind]}">{right_html or "&nbsp;"}</td>'
            "</tr>"
        )
    return ('<div class="cm-diff-wrap"><table class="cm-diff">'
            '<thead><tr><th colspan="3">Original</th><th colspan="3">Corrected</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')
