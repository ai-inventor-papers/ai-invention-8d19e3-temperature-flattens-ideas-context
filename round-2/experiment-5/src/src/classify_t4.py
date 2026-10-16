"""Classifier 'v1+T4' for the reserved k-th-smallest task (TAXONOMY_SELECT).

Same code extraction / comment+docstring stripping as v1 (classify.extract_code / strip_code), then
module-level rules applied in a fixed precedence:
Median_of_medians > Quickselect > Binary_search_value > Heap_select > Counting_bucket > Partial_selection
> Builtin > Sort_index > Other.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from classify import extract_code, sort_unit_label, strip_code

CLASSIFIER_T4_VERSION = "v1+T4"
R = lambda p: re.compile(p, re.I)  # noqa: E731

MOM = R(r"\[\s*\w+\s*:\s*\w+\s*\+\s*5\s*\]|range\(\s*0\s*,\s*len\([^)\n]*\)\s*,\s*5\s*\)|median_of_medians|"
        r"medians\b|chunks?\s*=|groups?\s*=\s*\[\s*\w+\[\s*\w+\s*:\s*\w+\s*\+\s*5")
MOM_FIVE = R(r"\b5\b")
PIVOT = R(r"pivot|partition")
KCMP = re.compile(r"(==|!=|<=|>=|<|>)\s*\(?\s*\bk\b|\bk\b\s*(-\s*1\s*)?\)?\s*(==|!=|<=|>=|<(?!<)|>(?!>))|"
                  r"(==|!=|<=|>=|<|>)\s*\(?\s*(k_?idx|k_?index|target|kth|k_minus_1|index)\b|"
                  r"\b(k_?idx|k_?index|target|kth)\b\s*(==|!=|<=|>=|<|>)")
BSV_MID = R(r"\bmid\b|\bmiddle\b|\bguess\b")
BSV_RANGE = R(r"min\(|max\(|\blo\b|\blow\b|\bleft\b")
BSV_LE = R(r"<=?\s*\(?\s*(mid|middle|guess)\b|\b(mid|middle|guess)\s*>=?|"
           r"\w*(count|num|less|le|rank)\w*\([^)\n]*\b(mid|middle|guess)\b")
BSV_COUNT = R(r"sum\(|count|len\(\s*\[")
HEAP = R(r"heapq|heappush|heappop|heapify|heappushpop|heapreplace|priorityqueue|"
         r"sift_?down|sift_?up|_heapify|max_?heap|min_?heap")
COUNTB = R(r"\bCounter\(|count\w*\s*=\s*\[\s*0\s*\]\s*\*|count\w*\s*\[[^\]\n]+\]\s*\+=\s*1|bucket|"
           r"cumulative|freq\w*\s*\[[^\]\n]+\]\s*\+=\s*1|defaultdict\(\s*int\s*\)")
PARTIAL = R(r"for\s+\w+\s+in\s+range\(\s*(k|k\s*-\s*1|0\s*,\s*k|0\s*,\s*k\s*-\s*1)\s*\)|while\s+k\b|"
            r"for\s+_\s+in\s+range\(\s*k")
PARTIAL_EXTRACT = R(r"\bmin\(|\.remove\(|\.pop\(|min_?(idx|index|i|pos|val\w*)\b|smallest|"
                    r"\w+\[\s*\w+\s*\]\s*<\s*\w+\[\s*min")
BUILTIN = R(r"np\.partition|argpartition|numpy\.partition|import\s+statistics|statistics\.|\.nsmallest\(|"
            r"import\s+numpy|from\s+numpy|pandas")
SORT = R(r"\bsorted\(|\.sort\(")
VALIDATION_NEXT = R(r"raise|return\s+None|return\s+-1|return\s+float|return\s+\"|return\s+'|print\(")


def classifier_t4_hash() -> str:
    h = hashlib.sha256(Path(__file__).read_bytes())
    h.update((Path(__file__).resolve().parent / "classify.py").read_bytes())
    return h.hexdigest()[:12]


def _drop_validation(src: str) -> str:
    """Remove `if ...:` guards whose body is a raise/return-None/print (input validation compares k too)."""
    lines = src.splitlines()
    out, skip = [], set()
    for i, ln in enumerate(lines):
        if i in skip:
            continue
        s = ln.strip()
        if s.startswith(("if ", "elif ")) and s.endswith(":") and i + 1 < len(lines) \
                and VALIDATION_NEXT.search(lines[i + 1]):
            skip.add(i + 1)
            continue
        if s.startswith(("if ", "elif ")) and ":" in s and VALIDATION_NEXT.search(s.split(":", 1)[1]):
            continue
        out.append(ln)
    return "\n".join(out)


def _recursive(src: str) -> bool:
    names = re.findall(r"^\s*def\s+(\w+)", src, re.M)
    for n in names:
        body_calls = len(re.findall(rf"\b{re.escape(n)}\s*\(", src))
        if body_calls >= 2:  # definition + at least one call (incl. a recursive one or a top-level call)
            # require a call inside its own body: crude check - text after the def line up to the next def
            m = re.search(rf"^(\s*)def\s+{re.escape(n)}\s*\(.*?$(.*?)(?=^\1def\s|\Z)", src, re.M | re.S)
            if m and re.search(rf"\b{re.escape(n)}\s*\(", m.group(2)):
                return True
    return False


def label_select(stripped: str) -> tuple[str, list[str]]:
    """Return (label, all_matching_rules_in_precedence_order)."""
    s = stripped
    sv = _drop_validation(s)
    hits = []
    if MOM.search(s) and MOM_FIVE.search(s) and re.search(r"median", s, re.I):
        hits.append("Median_of_medians")
    if PIVOT.search(s) and KCMP.search(sv):
        hits.append("Quickselect")
    if BSV_MID.search(s) and BSV_RANGE.search(s) and BSV_LE.search(s) and BSV_COUNT.search(s) \
            and re.search(r"min\(|max\(", s):
        hits.append("Binary_search_value")
    if HEAP.search(s):
        hits.append("Heap_select")
    if COUNTB.search(s):
        hits.append("Counting_bucket")
    if PARTIAL.search(s) and PARTIAL_EXTRACT.search(s):
        hits.append("Partial_selection")
    if BUILTIN.search(s):
        hits.append("Builtin")
    if SORT.search(s) or sort_unit_label(s, _recursive(s)) != "Other":
        hits.append("Sort_index")
    return (hits[0] if hits else "Other"), hits


def classify_t4(text: str) -> dict:
    code, lang = extract_code(text)
    if code is None or not code.strip():
        return dict(label="Unparseable", multi=False, multi_labels=[], raw_labels=[], is_python=False,
                    oracle_eligible=False, code="", stripped="", lang=lang)
    stripped, tree, is_py = strip_code(code)
    non_py = (not is_py) and (lang not in ("python", "py", "python3", "", "python?") or "{" in stripped)
    label, hits = label_select(stripped)
    return dict(label=label, multi=len(hits) > 1, multi_labels=hits, raw_labels=hits, is_python=is_py and not non_py,
                oracle_eligible=bool(is_py and not non_py), code=code, stripped=stripped, lang=lang)
