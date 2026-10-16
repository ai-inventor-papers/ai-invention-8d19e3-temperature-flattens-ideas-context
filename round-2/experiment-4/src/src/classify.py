"""Code extraction + rule-based idea classifier (graph and sort taxonomies).

Comments and docstrings are stripped BEFORE classification (the llm-creativity repo bug: ban names echoed
into docstrings fooled its rule classifier). Classifier version is frozen via CLASSIFIER_VERSION + file hash.
"""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

CLASSIFIER_VERSION = "v1"

FENCE_RE = re.compile(r"```[ \t]*([\w+#-]*)[^\n]*\n(.*?)(?:```|\Z)", re.S)


def classifier_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]


# ----------------------------------------------------------------------------- extraction
def extract_code(text: str) -> tuple[str | None, str]:
    """Return (code, lang_tag). Main block = longest fenced block containing def/class."""
    blocks = [(m.group(1).lower(), m.group(2)) for m in FENCE_RE.finditer(text)]
    if blocks:
        py = [b for b in blocks if b[0] in ("python", "py", "python3", "")]
        cand = py or blocks
        with_def = [b for b in cand if re.search(r"^\s*(def|class)\s", b[1], re.M)]
        if not with_def:
            with_def = [b for b in blocks if re.search(r"\b(def|class|function|void|int|public)\b", b[1])]
        pool = with_def or cand
        lang, code = max(pool, key=lambda b: len(b[1]))
        return code, lang
    try:
        ast.parse(text)
        if re.search(r"^\s*def\s", text, re.M):
            return text, "python"
    except SyntaxError:
        pass
    # unfenced code mixed with prose: take from the first 'def'/'import' line
    m = re.search(r"^(def |import |from \w+ import|class )", text, re.M)
    if m:
        return text[m.start():], "python?"
    return None, ""


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
            # also drop any bare string expressions (comment-like) in bodies
            node.body = [s for s in node.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                                                       and isinstance(s.value.value, str))] or [ast.Pass()]
    return tree


def _parse_lenient(code: str) -> ast.Module | None:
    """ast.parse; on failure (e.g. truncated output) drop trailing lines until it parses (max 60)."""
    try:
        return ast.parse(code)
    except (SyntaxError, ValueError):
        pass
    lines = code.splitlines()
    for k in range(1, min(60, len(lines))):
        try:
            return ast.parse("\n".join(lines[:-k]))
        except (SyntaxError, ValueError):
            continue
    return None


def regex_strip(code: str) -> str:
    code = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', "", code)
    code = re.sub(r"/\*[\s\S]*?\*/", "", code)
    code = re.sub(r"(?m)#.*$", "", code)
    code = re.sub(r"(?m)//.*$", "", code)
    return code


def strip_code(code: str) -> tuple[str, ast.Module | None, bool]:
    """Return (stripped_source, tree_or_None, is_python)."""
    tree = _parse_lenient(code)
    if tree is not None:
        tree = _strip_docstrings(tree)
        try:
            src = ast.unparse(tree)
            return src, ast.parse(src), True
        except (ValueError, SyntaxError, RecursionError):
            pass
    return regex_strip(code), None, False


# ----------------------------------------------------------------------------- function units
HELPER_NAMES = re.compile(r"^(reconstruct\w*|build_path|get_path|path_to|heuristic\w*|h|print\w*|main|__init__|"
                          r"add_edge|add_node|add_vertex|__\w+__|test\w*|neighbors?|get_neighbors?|is_valid\w*|"
                          r"display\w*|show\w*|draw\w*|example\w*|swap|manhattan\w*|euclid\w*|distance)$", re.I)


def _calls_self(fn: ast.AST) -> bool:
    names = {n.name for n in ast.walk(fn) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
            if nm in names:
                return True
    return False


def function_units(tree: ast.Module) -> list[tuple[str, str, bool]]:
    """(name, source, recursive) for each top-level function and class method, in source order."""
    units: list[tuple[int, str, str, bool]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            units.append((node.lineno, node.name, ast.unparse(node), _calls_self(node)))
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    units.append((sub.lineno, sub.name, ast.unparse(sub), _calls_self(sub)))
    units.sort()
    return [(n, s, r) for _, n, s, r in units]


def zero_heuristic(tree: ast.Module | None, src: str) -> bool:
    if re.search(r"lambda[^:]*:\s*0\b", src) and re.search(r"heuristic|\bh\b", src):
        return True
    if tree is None:
        return False
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and re.match(r"(heuristic\w*|h)$", n.name):
            body = [s for s in n.body if not isinstance(s, ast.Pass)]
            if len(body) == 1 and isinstance(body[0], ast.Return) and isinstance(body[0].value, ast.Constant) \
                    and body[0].value.value == 0:
                return True
    return False


# ----------------------------------------------------------------------------- graph detectors
R = lambda p: re.compile(p, re.I)  # noqa: E731
G_HEAP = R(r"heapq|heappush|heappop|priorityqueue|heapify|\.sort\(|sorted\(|min\([^)\n]*key\s*=|"
           r"min_dist\w*|min_node|min_vertex|smallest|min_distance|extract_min|decrease_key")
G_FIFO = R(r"popleft\(|\.pop\(0\)|\bqueue\.get\(|\bq\.get\(|simplequeue|queue\.queue\(")
G_STACK = R(r"\.pop\(\s*\)|\.pop\(-1\)|lifoqueue")
G_RELAX_CMP = R(r"(\w+\[[^\]\n]+\]\s*\+\s*[^\n<>=]*<(?!=))|(<\s*(self\.)?\w*(dist|cost|score|distance|d|g)\w*\[)|"
                r"(\b(new_?\w*|alt\w*|tentative\w*|candidate\w*|cost|distance|new_cost|new_dist|nd|ndist|"
                r"total\w*|g\w*)\s*<\s*\w)")
G_WEIGHT_ADD = R(r"\+\s*(weight|w|wt|cost|edge_cost|edge_weight|length|distance|d|weight_\w+|edge\w*|c)\b|"
                 r"\+\s*(self\.)?(graph|adj\w*|edges|g|weights?)\[")
G_HEUR = R(r"heuristic|manhattan|euclid|\bh\(|h_score|hscore|f_score|fscore|\bsqrt\(|hypot|\babs\(|\bh_cost\b")
G_GCOST = R(r"g_score|gscore|\bg_cost\b|cost_so_far|path_cost|\btentative|\+\s*(self\.)?(heuristic\w*|h)\(|"
            r"\bg\s*\+|\+\s*h\b|g\[|\bnew_cost\b|\bcost\s*\+|\bdist\w*\[[^\]]+\]\s*\+")
G_FLOYD = R(r"\[\s*(\w+)\s*\]\s*\[\s*(\w+)\s*\]\s*\+\s*\w+\s*\[\s*\2\s*\]\s*\[\s*(\w+)\s*\]")
G_BELLMAN = R(r"range\(\s*(len\([^)\n]*\)|\w+|self\.\w+|len\(\w+\.\w+\))\s*-\s*1\s*\)|bellman")
G_IDDFS = R(r"depth_limit|max_depth|depth\s*-\s*1|limit\s*-\s*1|iterative_deepening|iddfs|\bdls\b|"
            r"for\s+(depth|limit|d|max_d\w*|lim)\s+in\s+(range|itertools\.count|count)\(")
G_BIDIR = R(r"forward|backward|bidirectional|from_start|from_goal|from_end|from_target|"
            r"(visited|queue|frontier|parents?|dist)_(start|goal|end|src|dst|source|target|s|t|f|b|fwd|bwd)\b|"
            r"\b(start|goal|end|src|dst|source|target|fwd|bwd|front|back)_(visited|queue|frontier|parents?|dist)\b|"
            r"intersect")
G_VISITED = R(r"visited|seen|explored|closed|discovered|parent|came_from|\bprev\b|predecessor")


def graph_unit_label(s: str, recursive: bool, zero_h: bool) -> str:
    heap = bool(G_HEAP.search(s))
    fifo = bool(G_FIFO.search(s))
    stack = bool(G_STACK.search(s)) and not heap
    relax = bool(G_RELAX_CMP.search(s))
    wadd = bool(G_WEIGHT_ADD.search(s))
    heur = bool(G_HEUR.search(s)) and not zero_h
    if G_FLOYD.search(s):
        return "Floyd_Warshall"
    nfrontier = len(re.findall(r"popleft\(|\.pop\(0\)|heappop\(|\.pop\(\s*\)", s))
    if G_BIDIR.search(s) and nfrontier >= 2:
        return "Bidirectional"
    if heap and heur:
        return "A_star" if G_GCOST.search(s) else "Greedy_best_first"
    if G_BELLMAN.search(s) and (relax or wadd):
        return "Bellman_Ford"
    if fifo and relax and not heap:
        return "SPFA"
    if heap and (relax or wadd):
        return "Dijkstra"
    if G_IDDFS.search(s) and (recursive or stack):
        return "IDDFS"
    if fifo and not heap:
        return "BFS"
    if (stack or recursive) and G_VISITED.search(s):
        return "DFS"
    if heap and re.search(r"heappush|put\(", s):
        return "Dijkstra"
    return "Other"


# ----------------------------------------------------------------------------- sort detectors
S_TIM = R(r"min_?run|\btimsort\b|tim_sort|\bRUN\b")
S_RADIX = R(r"//\s*exp|\bexp\s*\*=\s*10|\bradix|//\s*(place|divisor|digit_place|power)|\bdigit\w*\s*=|%\s*10\b")
S_BUCKET = R(r"bucket")
S_COUNT = R(r"\bcount\w*\s*\[[^\]\n]*\]\s*\+=\s*1|\bcount\w*\s*=\s*\[\s*0\s*\]\s*\*|counting")
S_SHELL = R(r"\bgap\b|\binterval\b|\bshell")
S_HEAP = R(r"heapify|sift_?down|sift_?up|heappop|\bheap_?sort|2\s*\*\s*\w+\s*\+\s*1")
S_QUICK = R(r"pivot|partition")
S_MERGE_SPLIT = R(r"(//\s*2|>>\s*1)")
S_MERGE_JOIN = R(r"while\s+\w+\s*<\s*len\([^)]*\)\s+and\s+\w+\s*<\s*len\(|\bmerge\w*\(")
S_INSERT = R(r"while\s+\w+\s*>=\s*0\s+and\s+\w+\[\w+\]\s*>\s*\w+|\bkey\s*=\s*\w+\[\w+\]|insertion|"
             r"while\s+\w+\s*>\s*0\s+and\s+\w+\[\w+\s*-\s*1\]\s*>")
S_SELECT = R(r"\bmin_?(idx|index|i|pos|position)\b|\bmax_?(idx|index|i|pos)\b|\bselection|\bsmallest\b")
S_BUBBLE = R(r"\[\s*\w+\s*\+\s*1\s*\]\s*,\s*\w+\[\s*\w+\s*\]\s*=|\bswapped\b|bubble|"
             r"\w+\[\s*(\w+)\s*\]\s*>\s*\w+\[\s*\1\s*\+\s*1\s*\]|\w+\[\s*(\w+)\s*\+\s*1\s*\]\s*<\s*\w+\[\s*\2\s*\]")


def sort_unit_label(s: str, recursive: bool) -> str:
    if S_TIM.search(s):
        return "Tim_hybrid"
    if S_RADIX.search(s) and re.search(r"//|digit|radix", s, re.I):
        return "Radix"
    if S_BUCKET.search(s):
        return "Bucket"
    if S_COUNT.search(s):
        return "Counting"
    if S_SHELL.search(s):
        return "Shell"
    if S_HEAP.search(s):
        return "Heap"
    if S_QUICK.search(s) and (recursive or re.search(r"partition|stack|\.append\(\(", s, re.I)):
        return "Quick"
    if (S_MERGE_SPLIT.search(s) and recursive) or S_MERGE_JOIN.search(s) and re.search(r"merge|left|right", s, re.I):
        return "Merge"
    if S_INSERT.search(s):
        return "Insertion"
    if S_SELECT.search(s):
        return "Selection"
    if S_BUBBLE.search(s):
        return "Bubble"
    if S_QUICK.search(s):
        return "Quick"
    return "Other"


# composite precedence: composite idea subsumes its helper ideas
SUBSUMES = {
    "IDDFS": {"DFS"}, "Bidirectional": {"BFS", "DFS", "Dijkstra"}, "A_star": {"Dijkstra"},
    "Tim_hybrid": {"Insertion", "Merge", "Bubble"}, "Radix": {"Counting", "Bucket", "Insertion"},
    "Bucket": {"Insertion", "Quick", "Merge", "Selection", "Bubble"},
    "Merge": set(), "Heap": set(), "Quick": {"Insertion"},
}


def classify_text(text: str, kind: str) -> dict:
    """Return dict(label, multi, multi_labels, raw_labels, is_python, oracle_eligible, code, stripped)."""
    code, lang = extract_code(text)
    if code is None or not code.strip():
        return dict(label="Unparseable", multi=False, multi_labels=[], raw_labels=[], is_python=False,
                    oracle_eligible=False, code="", stripped="", lang=lang)
    stripped, tree, is_py = strip_code(code)
    non_py = (not is_py) and (lang not in ("python", "py", "python3", "", "python?") or "{" in stripped)
    raw: list[str] = []
    zero_h = zero_heuristic(tree, stripped)
    if tree is not None:
        units = function_units(tree)
        for name, src, rec in units:
            if HELPER_NAMES.match(name):
                continue
            lab = graph_unit_label(src, rec, zero_h) if kind == "graph" else sort_unit_label(src, rec)
            if lab != "Other":
                raw.append(lab)
        if not raw:  # module-level script implementation
            lab = graph_unit_label(stripped, False, zero_h) if kind == "graph" else sort_unit_label(stripped, False)
            if lab != "Other":
                raw.append(lab)
    else:
        rec = bool(re.search(r"(\w+)\s*\([^)]*\)[\s\S]*\b\1\s*\(", stripped)) and kind == "sort"
        lab = graph_unit_label(stripped, rec, zero_h) if kind == "graph" else sort_unit_label(stripped, rec)
        if lab != "Other":
            raw.append(lab)
    distinct: list[str] = []
    for r_ in raw:
        if r_ not in distinct:
            distinct.append(r_)
    subsumed = set().union(*[SUBSUMES.get(d, set()) for d in distinct]) if distinct else set()
    kept = [d for d in distinct if d not in subsumed] or distinct
    if kind == "sort" and not kept:
        if re.search(r"\bsorted\(|\.sort\(", stripped):
            kept = ["Builtin"]
    label = kept[0] if kept else "Other"
    return dict(label=label, multi=len(kept) > 1, multi_labels=kept, raw_labels=raw, is_python=is_py and not non_py,
                oracle_eligible=bool(is_py and not non_py), code=code, stripped=stripped, lang=lang)


# ----------------------------------------------------------------------------- idea lexicon for co-mention parsing
LEXICON_GRAPH = [
    ("IDDFS", r"iterative[\s-]*deepening|iddfs"), ("Bidirectional", r"bi-?directional"),
    ("Greedy_best_first", r"greedy|best[\s-]*first"), ("A_star", r"\ba\s*\*|a-star|astar|a star"),
    ("Bellman_Ford", r"bellman"), ("SPFA", r"spfa|shortest path faster"), ("Floyd_Warshall", r"floyd|warshall"),
    ("Dijkstra", r"dijkstra|uniform[\s-]*cost"), ("BFS", r"breadth|\bbfs\b"), ("DFS", r"depth|\bdfs\b"),
]
LEXICON_SORT = [
    ("Tim_hybrid", r"tim\s*sort|timsort|introsort|hybrid"), ("Quick", r"quick"), ("Merge", r"merge"),
    ("Heap", r"heap"), ("Insertion", r"insertion"), ("Selection", r"selection"), ("Bubble", r"bubble"),
    ("Shell", r"shell"), ("Counting", r"counting"), ("Radix", r"radix"), ("Bucket", r"bucket"),
]


def parse_list_names(text: str, kind: str) -> list[str]:
    """Parse a numbered list into taxonomy classes in rank order (dedup; unmatched -> Other)."""
    lex = LEXICON_GRAPH if kind == "graph" else LEXICON_SORT
    out: list[str] = []
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)[\.\):]\s*(.+)", line)
        if not m:
            continue
        item = m.group(2)
        cls = "Other"
        for c, pat in lex:
            if re.search(pat, item, re.I):
                cls = c
                break
        out.append(cls)
    return out
