"""Deterministic AST + identifier rule classifier of the implemented solution idea.

Path tasks (T1 'path search', T3 'weighted shortest path') share one taxonomy;
T2 (sorting) has its own. Each top-level unit (function or class) is classified
independently; the response label is the label of the first ROOT algorithm unit
(an algorithm unit not called by another algorithm unit). Rules are applied in
the precedence order of the pre-registered plan.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from .extract import declared_idea, extract_code

PATH_LABELS = ["bfs", "dfs", "dijkstra", "a_star", "greedy_best_first", "bidirectional",
               "bellman_ford_spfa", "floyd_warshall", "iddfs_idastar", "uniform_cost_other", "other"]
SORT_LABELS = ["bubble", "selection", "insertion", "merge", "quick", "heap", "shell",
               "counting", "radix", "bucket", "builtin_wrapper", "other"]

HEUR_RE = re.compile(r"(heur|manhattan|euclid|estimate|octile|chebyshev|haversine|^h$|^h_?(cost|score|val|value)?$|dist_to_goal|distance_to_goal)", re.I)
NX_SP_RE = re.compile(r"(shortest_path|dijkstra|astar_path|bellman_ford|bfs_tree|dfs_tree|bidirectional|floyd_warshall|single_source|all_pairs|has_path)", re.I)


@dataclass
class UnitFeatures:
    name: str
    calls: set = field(default_factory=set)          # called function/method names
    call_owner: dict = field(default_factory=dict)   # method name -> owners
    idents: set = field(default_factory=set)         # all identifiers (lowercased)
    n_for: int = 0
    n_while: int = 0
    max_for_depth: int = 0
    pop0: bool = False
    pop_noarg: bool = False
    appendleft: bool = False
    self_recursive: bool = False
    recursion_in_loop: bool = False
    floyd_pattern: bool = False
    bellman_pattern: bool = False
    relax_pattern: bool = False
    adj_swap_compare: bool = False
    heap_priorities: list = field(default_factory=list)
    add_with_heur: bool = False
    has_add: bool = False
    depth_loop_call: bool = False
    slice_mid_recursion: bool = False
    floordiv_mod: bool = False
    count_augassign: bool = False
    nx_call: bool = False
    called_user_units: set = field(default_factory=set)
    n_frontiers: int = 0


def _name_of_call(node: ast.Call) -> tuple[str, str]:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id, ""
    if isinstance(f, ast.Attribute):
        owner = ""
        if isinstance(f.value, ast.Name):
            owner = f.value.id
        elif isinstance(f.value, ast.Attribute):
            owner = f.value.attr
        return f.attr, owner
    return "", ""


def _contains(node: ast.AST, pred) -> bool:
    return any(pred(n) for n in ast.walk(node))


def _is_heur_expr(node: ast.AST, h_vars: set) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            nm, _ = _name_of_call(n)
            if nm and HEUR_RE.search(nm):
                return True
        if isinstance(n, ast.Name) and (n.id in h_vars or HEUR_RE.search(n.id)):
            return True
        if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and HEUR_RE.search(n.value.id):
            return True
    return False


def _subscript_chain(node: ast.AST) -> tuple[str | None, list[str]]:
    """X[a][b] -> ('X', ['a','b']) for Name indices; supports X[a, b] too."""
    idx: list[str] = []
    cur = node
    while isinstance(cur, ast.Subscript):
        s = cur.slice
        if isinstance(s, ast.Tuple):
            idx = [e.id if isinstance(e, ast.Name) else "?" for e in s.elts] + idx
        else:
            idx.insert(0, s.id if isinstance(s, ast.Name) else "?")
        cur = cur.value
    if isinstance(cur, ast.Name):
        return cur.id, idx
    if isinstance(cur, ast.Attribute):
        return cur.attr, idx
    return None, idx


def _unit_features(unit: ast.AST, unit_name: str, user_units: set) -> UnitFeatures:
    uf = UnitFeatures(name=unit_name)
    method_names = {n.name for n in ast.walk(unit) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    h_vars: set = set()
    # identifiers
    for n in ast.walk(unit):
        if isinstance(n, ast.Name):
            uf.idents.add(n.id.lower())
        elif isinstance(n, ast.arg):
            uf.idents.add(n.arg.lower())
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            uf.idents.add(n.name.lower())
        elif isinstance(n, ast.Attribute):
            uf.idents.add(n.attr.lower())
        elif isinstance(n, ast.Assign):
            if _is_heur_expr(n.value, set()) and not isinstance(n.value, ast.BinOp):
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        h_vars.add(t.id)
    # calls
    for n in ast.walk(unit):
        if isinstance(n, ast.Call):
            nm, owner = _name_of_call(n)
            if not nm:
                continue
            uf.calls.add(nm)
            uf.call_owner.setdefault(nm, set()).add(owner)
            if nm in user_units and nm != unit_name:
                uf.called_user_units.add(nm)
            if nm == "pop" and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == 0:
                uf.pop0 = True
            if nm == "pop" and not n.args:
                uf.pop_noarg = True
            if nm == "appendleft":
                uf.appendleft = True
            if owner in ("nx", "networkx", "csgraph", "graph_tool", "igraph") and NX_SP_RE.search(nm):
                uf.nx_call = True
            if nm in ("heappush", "put", "heappushpop", "heapreplace") and len(n.args) >= (2 if nm != "put" else 1):
                item = n.args[1] if nm != "put" else n.args[0]
                pri = item.elts[0] if isinstance(item, ast.Tuple) and item.elts else item
                uf.heap_priorities.append(pri)
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            uf.has_add = True
            if _is_heur_expr(n, h_vars):
                uf.add_with_heur = True
        if isinstance(n, ast.AugAssign) and isinstance(n.op, ast.Add):
            uf.has_add = True
            if isinstance(n.target, ast.Subscript):
                base, _ = _subscript_chain(n.target)
                if base and "count" in base.lower():
                    uf.count_augassign = True
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod):
            if _contains(n.left, lambda x: isinstance(x, ast.BinOp) and isinstance(x.op, ast.FloorDiv)):
                uf.floordiv_mod = True
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
            nm, _ = _name_of_call(n.value)
            if nm in ("deque", "Queue", "PriorityQueue", "LifoQueue", "SimpleQueue"):
                uf.n_frontiers += 1
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.List):
            for t in n.targets:
                if isinstance(t, ast.Name) and re.search(r"queue|frontier|open|stack|fringe", t.id, re.I):
                    uf.n_frontiers += 1
    # self recursion
    self_names = {unit_name} | method_names
    for loop in [n for n in ast.walk(unit) if isinstance(n, (ast.For, ast.While))]:
        for c in ast.walk(loop):
            if isinstance(c, ast.Call):
                nm, _ = _name_of_call(c)
                if nm in self_names and nm not in ("__init__",):
                    uf.recursion_in_loop = True
    for fn in [n for n in ast.walk(unit) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        for c in ast.walk(fn):
            if isinstance(c, ast.Call):
                nm, _ = _name_of_call(c)
                if nm == fn.name:
                    uf.self_recursive = True
                    # merge-sort style recursion on slices with a mid index
                    for a in c.args:
                        if isinstance(a, ast.Subscript) and isinstance(a.slice, ast.Slice):
                            uf.slice_mid_recursion = True
    # loops / nesting
    def walk_loops(node: ast.AST, depth: int, fors: list) -> None:
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, ast.For):
                uf.n_for += 1
                uf.max_for_depth = max(uf.max_for_depth, depth + 1)
                tgt = ch.target.id if isinstance(ch.target, ast.Name) else "?"
                walk_loops(ch, depth + 1, fors + [(tgt, ch)])
            elif isinstance(ch, ast.While):
                uf.n_while += 1
                walk_loops(ch, depth, fors)
            else:
                if isinstance(ch, ast.BinOp) and isinstance(ch.op, ast.Add) and len(fors) >= 3:
                    lb, li = _subscript_chain(ch.left)
                    rb, ri = _subscript_chain(ch.right)
                    vars_ = [f[0] for f in fors]
                    if lb and rb and len(li) == 2 and len(ri) == 2 and li[1] == ri[0] and li[1] in vars_:
                        uf.floyd_pattern = True
                walk_loops(ch, depth, fors)
    walk_loops(unit, 0, [])
    # relaxation: compare  X[u] + w < X[v]  (either side order)
    for n in ast.walk(unit):
        if isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.ops[0], (ast.Lt, ast.Gt, ast.LtE, ast.GtE)):
            sides = [n.left, n.comparators[0]]
            if any(isinstance(s, ast.BinOp) and isinstance(s.op, ast.Add) and isinstance(s.left, ast.Subscript) for s in sides) \
                    and any(isinstance(s, ast.Subscript) for s in sides):
                uf.relax_pattern = True
            # bubble: arr[j] > arr[j + 1]
            l, r = sides
            if isinstance(l, ast.Subscript) and isinstance(r, ast.Subscript):
                ls, rs = l.slice, r.slice
                if isinstance(ls, ast.Name) and isinstance(rs, ast.BinOp) and isinstance(rs.left, ast.Name) \
                        and rs.left.id == ls.id and isinstance(rs.op, ast.Add):
                    uf.adj_swap_compare = True
                if isinstance(rs, ast.Name) and isinstance(ls, ast.BinOp) and isinstance(ls.left, ast.Name) \
                        and ls.left.id == rs.id and isinstance(ls.op, (ast.Add, ast.Sub)):
                    uf.adj_swap_compare = True
    # Bellman-Ford: for _ in range(len(X) - 1) / range(n - 1) containing a relaxation
    for n in ast.walk(unit):
        if isinstance(n, ast.For) and isinstance(n.iter, ast.Call) and _name_of_call(n.iter)[0] == "range":
            args = n.iter.args
            if args and isinstance(args[-1] if len(args) == 1 else args[1], ast.BinOp):
                a = args[-1] if len(args) == 1 else args[1]
                if isinstance(a.op, ast.Sub) and isinstance(a.right, ast.Constant) and a.right.value == 1:
                    inner_relax = any(
                        isinstance(c, ast.Compare) and any(isinstance(s, ast.BinOp) and isinstance(s.op, ast.Add)
                                                           for s in [c.left] + list(c.comparators))
                        for c in ast.walk(n))
                    inner_loop = any(isinstance(c, ast.For) for c in ast.walk(n) if c is not n)
                    if inner_relax and inner_loop:
                        uf.bellman_pattern = True
    # iterative deepening: for d in range(...): ... call(..., d, ...)
    for n in ast.walk(unit):
        if isinstance(n, (ast.For,)) and isinstance(n.target, ast.Name):
            v = n.target.id
            if re.search(r"depth|limit|bound|d$", v, re.I) or (isinstance(n.iter, ast.Call) and _name_of_call(n.iter)[0] == "count"):
                for c in ast.walk(n):
                    if isinstance(c, ast.Call) and any(isinstance(a, ast.Name) and a.id == v for a in c.args):
                        nm, _ = _name_of_call(c)
                        if nm not in ("range", "print", "len", "append", "str", "format"):
                            uf.depth_loop_call = True
    return uf


def _ident_has(uf: UnitFeatures, pat: str) -> bool:
    r = re.compile(pat, re.I)
    return any(r.search(i) for i in uf.idents)


def classify_path_unit(uf: UnitFeatures) -> tuple[str, str]:
    heap = bool({"heappush", "heappop", "heapify", "PriorityQueue"} & uf.calls) or \
        ("put" in uf.calls and "PriorityQueue" in uf.calls)
    bfs_q = uf.pop0 or ("popleft" in uf.calls) or (("get" in uf.calls) and ("Queue" in uf.calls or "SimpleQueue" in uf.calls))
    # 1 bidirectional
    if _ident_has(uf, r"bidirect|bi_direct") or (
            _ident_has(uf, r"forward|_fwd|fwd_|front_") and _ident_has(uf, r"backward|_bwd|bwd_|back_")) or (
            uf.n_frontiers >= 2 and _ident_has(uf, r"(visited|queue|frontier|parent)s?_?(start|src|source|begin|f)\b|^(start|src|source|f)_?(visited|queue|frontier|parent)")
            and _ident_has(uf, r"(visited|queue|frontier|parent)s?_?(goal|end|target|dst|dest|b)\b|^(goal|end|target|dst|dest|b)_?(visited|queue|frontier|parent)")):
        return "bidirectional", ""
    # 2 floyd
    if uf.floyd_pattern or _ident_has(uf, r"floyd|warshall"):
        return "floyd_warshall", ""
    # 3 bellman-ford / spfa
    if _ident_has(uf, r"spfa") or (not heap and ("deque" in uf.calls or bfs_q) and uf.relax_pattern
                                   and _ident_has(uf, r"in_?q(ueue)?\b|inqueue|in_queue")):
        return "bellman_ford_spfa", "spfa"
    if uf.bellman_pattern or _ident_has(uf, r"bellman"):
        return "bellman_ford_spfa", "bellman_ford"
    # 4 iterative deepening
    if _ident_has(uf, r"iddfs|iterative_deepening|ida_?star|idastar|^ida$") or (
            uf.depth_loop_call and _ident_has(uf, r"limit|max_depth|depth")):
        return "iddfs_idastar", ""
    # 5 heap-based
    if heap:
        heur = (_ident_has(uf, HEUR_RE.pattern) or any(HEUR_RE.search(c) for c in uf.calls))
        if heur:
            pri_heur_only = any(_is_heur_expr(p, set()) and not _contains(p, lambda x: isinstance(x, ast.BinOp) and isinstance(x.op, ast.Add))
                                for p in uf.heap_priorities)
            if uf.add_with_heur or _ident_has(uf, r"^g_?(score|cost)?$|^f_?(score|cost)?$|astar|a_star"):
                return "a_star", ""
            if pri_heur_only:
                return "greedy_best_first", ""
            return "a_star", "heuristic_unclear"
        if _ident_has(uf, r"greedy|best_first"):
            return "greedy_best_first", "no_heuristic_name"
        if not uf.has_add:
            return "uniform_cost_other", ""
        return "dijkstra", ("ucs" if _ident_has(uf, r"uniform|ucs") else "")
    # 6 bfs
    if bfs_q:
        if uf.relax_pattern and _ident_has(uf, r"dist|cost"):
            return "bellman_ford_spfa", "queue_relaxation"
        return "bfs", ""
    # 7 dfs
    if (uf.pop_noarg and "append" in uf.calls and _ident_has(uf, r"stack|frontier|open|fringe|to_visit|todo")) \
            or uf.recursion_in_loop or (uf.self_recursive and _ident_has(uf, r"visit|neighbor|neighbour|adj|graph|path")):
        return "dfs", ""
    # dijkstra without heap (linear min-scan)
    if uf.relax_pattern and _ident_has(uf, r"dijkstra|unvisited|min_dist|min_node|shortest"):
        return "dijkstra", "linear_scan"
    if uf.pop_noarg and "append" in uf.calls and _ident_has(uf, r"visit|neighbor|neighbour|adj|graph"):
        return "dfs", "stack_unnamed"
    return "other", "unrecognized"


def classify_sort_unit(uf: UnitFeatures) -> tuple[str, str]:
    has_loops = (uf.n_for + uf.n_while) > 0
    uses_builtin = bool({"sorted", "sort"} & uf.calls)
    if uses_builtin and not has_loops and not uf.self_recursive:
        return "builtin_wrapper", ""
    if _ident_has(uf, r"radix") or (uf.floordiv_mod and _ident_has(uf, r"^exp$|place|digit|^div")):
        return "radix", ""
    if _ident_has(uf, r"counting") or (uf.count_augassign and _ident_has(uf, r"^counts?$|count_arr|count_array|^c$") and not _ident_has(uf, r"bucket")):
        return "counting", ""
    if _ident_has(uf, r"bucket"):
        return "bucket", ""
    if _ident_has(uf, r"heapify|sift|heap_sort|heapsort") or ({"heappush", "heappop"} <= uf.calls):
        return "heap", ""
    if _ident_has(uf, r"merge") or uf.slice_mid_recursion and _ident_has(uf, r"mid"):
        return "merge", ""
    if _ident_has(uf, r"pivot|partition|quick"):
        return "quick", ""
    if _ident_has(uf, r"^gap$|shell"):
        return "shell", ""
    if _ident_has(uf, r"insertion") or (_ident_has(uf, r"^key$|^current$|^temp$") and uf.n_while > 0 and uf.n_for > 0):
        return "insertion", ""
    if _ident_has(uf, r"min_?idx|min_?index|minimum_index|max_?idx|max_?index|selection|smallest"):
        return "selection", ""
    if _ident_has(uf, r"bubble|swapped") or uf.adj_swap_compare:
        return "bubble", ""
    if uses_builtin:
        return "builtin_wrapper", "with_loops"
    return "other", "unrecognized"


_NON_ALGO_NAME = re.compile(r"^(main|test|print|display|show|reconstruct|build|create|make|get_neighbou?rs?|neighbou?rs?|add_edge|is_valid|valid|heuristic|example|usage|demo|draw|read|parse|generate|random)", re.I)


def classify(code: str, task: str) -> dict:
    """Classify cleaned code. Returns {label, sublabel, features}."""
    if not code.strip():
        return {"label": "other", "sublabel": "no_code", "features": {}}
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return {"label": "other", "sublabel": "unparseable", "features": {}}
    units: list[tuple[str, ast.AST]] = []
    module_stmts: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            units.append((node.name, node))
        else:
            module_stmts.append(node)
    user_units = {n for n, _ in units}
    clf = classify_sort_unit if task == "T2" else classify_path_unit
    results = []
    for name, node in units:
        uf = _unit_features(node, name, user_units)
        lab, sub = clf(uf)
        results.append({"unit": name, "label": lab, "sublabel": sub, "calls_units": sorted(uf.called_user_units),
                        "nx": uf.nx_call})
    if module_stmts:
        mod = ast.Module(body=module_stmts, type_ignores=[])
        uf = _unit_features(mod, "<module>", user_units)
        # module-level code only counts if no unit is an algorithm
        lab, sub = clf(uf)
        results.append({"unit": "<module>", "label": lab, "sublabel": sub,
                        "calls_units": sorted(uf.called_user_units), "nx": uf.nx_call})
    algo = [r for r in results if r["label"] != "other" and r["unit"] != "<module>"]
    called = set()
    for r in algo:
        called |= set(r["calls_units"])
    roots = [r for r in algo if r["unit"] not in called]
    # deprioritise helper-named units (e.g. a recursive reconstruct_path) when a real one exists
    roots_main = [r for r in roots if not _NON_ALGO_NAME.match(r["unit"])] or roots
    feats = {"units": results}
    if roots_main:
        labels_seen = []
        for r in roots_main:
            if r["label"] not in labels_seen:
                labels_seen.append(r["label"])
        feats["all_ideas"] = labels_seen
        feats["multi"] = len(labels_seen) > 1
        return {"label": roots_main[0]["label"], "sublabel": roots_main[0]["sublabel"], "features": feats}
    mod_r = [r for r in results if r["unit"] == "<module>"]
    if mod_r and mod_r[0]["label"] != "other":
        feats["all_ideas"] = [mod_r[0]["label"]]
        feats["multi"] = False
        return {"label": mod_r[0]["label"], "sublabel": "module_level", "features": feats}
    if any(r["nx"] for r in results) and task != "T2":
        return {"label": "other", "sublabel": "library_call", "features": feats}
    if task == "T2" and any(r["sublabel"] == "" and r["label"] == "builtin_wrapper" for r in results):
        return {"label": "builtin_wrapper", "sublabel": "", "features": feats}
    return {"label": "other", "sublabel": "unrecognized", "features": feats}


def classify_text(text: str, task: str, partial_mode: bool = False) -> dict:
    """Full pipeline: extract -> classify -> declared label; partial_mode adds the
    prose fallback for truncated rollouts."""
    ex = extract_code(text)
    decl = declared_idea(text, task)
    if ex["parse_status"] in ("no_code", "unparseable"):
        res = {"label": "other", "sublabel": ex["parse_status"], "features": {}}
    else:
        res = classify(ex["code"], task)
    if partial_mode and res["label"] == "other" and decl is not None:
        res = {"label": decl, "sublabel": "declared_fallback", "features": res.get("features", {})}
    res["declared_label"] = decl
    res["parse_status"] = ex["parse_status"]
    res["code"] = ex["code"]
    res["has_fence"] = ex["has_fence"]
    return res
