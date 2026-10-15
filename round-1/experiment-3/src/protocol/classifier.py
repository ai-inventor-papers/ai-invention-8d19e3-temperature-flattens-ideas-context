"""Deterministic AST/keyword classifier of path-search programs into idea classes.

Comments and docstrings are stripped first (ast.parse -> drop Expr(Constant(str)) -> ast.unparse),
because ban lists and novelty instructions get echoed into docstrings and poison keyword rules
(lesson from DrejcPesjak/llm-creativity lc/rules.py:code_only). Rules are ordered; first match wins.
"""

from __future__ import annotations

import ast
import re

CODE_BLOCK_RE = re.compile(r"```[ \t]*(?:python|py|Python|python3)?[ \t]*\n(.*?)```", re.S)
OPEN_PY_RE = re.compile(r"```[ \t]*(?:python|py|Python|python3)[ \t]*\n(.*)$", re.S)


def extract_code(text: str) -> tuple[str | None, str]:
    """Return (code, how). Prefers the first ```python block; falls back to the largest code-like block."""
    m = re.search(r"```[ \t]*(?:python|py|Python|python3)[ \t]*\n(.*?)```", text, re.S)
    if m:
        return m.group(1), "python_block"
    blocks = CODE_BLOCK_RE.findall(text)
    blocks = [b for b in blocks if "def " in b]
    if blocks:
        return max(blocks, key=len), "largest_block"
    m = OPEN_PY_RE.search(text)  # unclosed (truncated) python block
    if m and "def " in m.group(1):
        return m.group(1), "unclosed_block"
    return None, "none"


def strip_code(code: str) -> tuple[str, ast.AST | None]:
    """Remove docstrings and comments. Returns (stripped_source, tree) or (code, None) on syntax error."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return code, None

    class _Strip(ast.NodeTransformer):
        def _clean(self, body: list) -> list:
            out = [s for s in body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                                           and isinstance(s.value.value, str))]
            return out or [ast.Pass()]

        def generic_visit(self, node: ast.AST) -> ast.AST:
            super().generic_visit(node)
            for field in ("body", "orelse", "finalbody"):
                if hasattr(node, field) and isinstance(getattr(node, field), list) and getattr(node, field):
                    if field == "body" or any(True for _ in getattr(node, field)):
                        setattr(node, field, self._clean(getattr(node, field)))
            return node

    tree = _Strip().visit(tree)
    ast.fix_missing_locations(tree)
    try:
        return ast.unparse(tree), tree
    except (ValueError, RecursionError):
        return code, tree


def _names(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            out.add(n.id.lower())
        elif isinstance(n, ast.arg):
            out.add(n.arg.lower())
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name.lower())
        elif isinstance(n, ast.Attribute):
            out.add(n.attr.lower())
    return out


def _max_for_depth(tree: ast.AST) -> int:
    best = 0

    def rec(node: ast.AST, d: int) -> None:
        nonlocal best
        for ch in ast.iter_child_nodes(node):
            nd = d + 1 if isinstance(ch, (ast.For, ast.comprehension)) else d
            best = max(best, nd)
            rec(ch, nd)

    rec(tree, 0)
    return best


def _recursive_funcs(tree: ast.AST) -> set[str]:
    rec = set()
    for f in ast.walk(tree):
        if isinstance(f, ast.FunctionDef):
            for n in ast.walk(f):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == f.name:
                    rec.add(f.name)
    return rec


def _receivers(tree: ast.AST, method: str) -> set[str]:
    """Names X for which X.method(...) is called (X may be attribute chain -> its unparsed form)."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == method:
            try:
                out.add(ast.unparse(n.func.value))
            except (ValueError, RecursionError):
                pass
    return out


def _heappop_args(tree: ast.AST) -> set[str]:
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            fn = n.func
            name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
            if name == "heappop" and n.args:
                try:
                    out.add(ast.unparse(n.args[0]))
                except (ValueError, RecursionError):
                    pass
    return out


HEUR_RE = re.compile(r"\b(heuristic\w*|h|manhattan\w*|euclid\w*|estimate\w*|h_score|h_cost|hfunc)\s*\(")


def classify_program(code: str | None) -> dict:
    """Return {'label', 'syntax_ok', 'stripped', 'features'}."""
    if code is None:
        return {"label": "no_code", "syntax_ok": False, "stripped": "", "features": {}}
    stripped, tree = strip_code(code)
    if tree is None:
        return {"label": "syntax_error", "syntax_ok": False, "stripped": stripped, "features": {}}
    s = stripped
    sl = s.lower()
    names = _names(tree)
    for_depth = _max_for_depth(tree)
    recf = _recursive_funcs(tree)
    pops_left = _receivers(tree, "popleft")
    pop0 = {r for r in _receivers(tree, "pop")} if re.search(r"\.pop\(\s*0\s*\)", s) else set()
    stack_pop = bool(re.search(r"\.pop\(\s*\)", s))
    q_get = bool(re.search(r"\.get\(\s*\)", s)) and ("queue" in sl)
    heap_args = _heappop_args(tree)
    uses_heap = bool(heap_args) or "heapq" in sl or "priorityqueue" in sl or "heappush" in sl
    min_select = bool(re.search(r"\bmin\([^\n]*key\s*=", s)) or bool(re.search(r"\.sort\(", s) and re.search(r"\.pop\(\s*0\s*\)", s))
    relax = bool(re.search(r"(\w+)\[\s*(\w+)\s*\]\s*\+\s*\w+\s*<\s*\w+\[", s)) or bool(
        re.search(r"<\s*\w+\[\s*\w+\s*\]", s) and re.search(r"\+\s*(weight|w|cost|edge_weight|wt)\b", s))
    heur_call = bool(HEUR_RE.search(s)) or any(n.startswith("heuristic") for n in names)
    heur_name = any(n.startswith("heuristic") or n in {"manhattan", "euclidean", "manhattan_distance",
                                                         "euclidean_distance"} for n in names)
    f_score = "f_score" in names or "fscore" in names or "f_cost" in names or "f_scores" in names
    feats = {"for_depth": for_depth, "recursive": sorted(recf), "popleft": sorted(pops_left),
             "pop0": bool(pop0), "stack_pop": stack_pop, "uses_heap": uses_heap, "heap_args": sorted(heap_args),
             "min_select": min_select, "relax": relax, "heur": heur_call or heur_name or f_score}

    # floyd_warshall: triple nested loop with dist[i][j] update via k
    if for_depth >= 3 and re.search(r"\[\s*(\w+)\s*\]\s*\[\s*(\w+)\s*\]", s) and re.search(
            r"\[\s*\w+\s*\]\s*\[\s*k\s*\]|\[\s*k\s*\]\s*\[\s*\w+\s*\]", s):
        return _r("floyd_warshall", s, feats)
    # bellman_ford: V-1 rounds of relaxation over all edges
    if re.search(r"range\(\s*len\([^)]*\)\s*-\s*1\s*\)|range\(\s*\w*(n|num_nodes|v|num_vertices|n_nodes)\w*\s*-\s*1\s*\)",
                 s, re.I) and for_depth >= 2 and not uses_heap:
        return _r("bellman_ford", s, feats)
    # spfa: FIFO queue + relaxation + in-queue tracking / re-enqueue on improvement (no heap)
    if (pops_left or pop0 or q_get) and relax and not uses_heap and (
            re.search(r"in_queue|inqueue|in_q\b|queued", sl) or re.search(r"not in (queue|q)\b", sl)):
        return _r("spfa", s, feats)
    # bidirectional: two frontiers expanded
    frontier_recv = set(pops_left) | set(heap_args)
    if len(frontier_recv) >= 2 or re.search(r"(forward|fwd|front|start|src|source)_?(queue|frontier|visited|q)\b", sl) and \
            re.search(r"(backward|bwd|back|goal|end|target|dst)_?(queue|frontier|visited|q)\b", sl):
        return _r("bidirectional", s, feats)
    # astar / greedy best-first: heuristic in priority
    if (uses_heap or min_select) and (heur_call or heur_name or f_score):
        if f_score or re.search(r"\+\s*(heuristic\w*|h|manhattan\w*|euclid\w*|estimate\w*)\s*\(", s) or re.search(
                r"(heuristic\w*|h|manhattan\w*|euclid\w*|estimate\w*)\s*\([^)]*\)\s*\+", s) or "g_score" in names:
            return _r("astar", s, feats)
        return _r("greedy_best_first", s, feats)
    # dijkstra: priority keyed by accumulated distance
    if uses_heap or (min_select and ("dist" in sl or "cost" in sl)):
        return _r("dijkstra", s, feats)
    # dial bucket
    if "bucket" in sl:
        return _r("dial_bucket", s, feats)
    # iddfs: depth-limited recursion inside increasing-depth loop
    if re.search(r"depth|limit", sl) and (recf or stack_pop) and re.search(r"for\s+\w*(depth|limit)\w*\s+in\s+range", sl):
        return _r("iddfs", s, feats)
    # bfs: FIFO frontier
    if pops_left or pop0 or q_get:
        return _r("bfs", s, feats)
    # dfs: explicit stack or recursion on neighbours
    if stack_pop or recf:
        return _r("dfs", s, feats)
    if re.search(r"random\.(choice|shuffle|random|sample|randint)", s):
        return _r("random_walk", s, feats)
    return _r("other", s, feats)


def _r(label: str, s: str, feats: dict) -> dict:
    return {"label": label, "syntax_ok": True, "stripped": s, "features": feats}


def classify_text(text: str) -> dict:
    code, how = extract_code(text)
    out = classify_program(code)
    out["code"] = code
    out["extract"] = how
    return out
