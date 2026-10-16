"""Sandboxed oracle runner (executed as `python -I oracle_runner.py <job.json>`).

Stdlib only. Loads the candidate program's DEFINITIONS (imports, defs, classes,
side-effect-free assignments), locates a callable, finds an input adapter that
yields well-formed output on a smoke instance, then evaluates 50 fixed instances.
Prints one JSON line with the result.
"""

import ast
import inspect
import io
import json
import math
import re
import resource
import signal
import sys
import contextlib


class _Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise _Timeout()


signal.signal(signal.SIGALRM, _alarm)

GRAPH_P = re.compile(r"^(graph|g|adj|adjacency|adj_list|adjacency_list|graph_dict|network|neighbors|neighbours|nodes|edges|edge_list|grid|maze|matrix|board|map|world|weighted_graph|adj_matrix|w|weights)$|graph|adj|edge|grid|maze|matrix", re.I)
START_P = re.compile(r"^(start|source|src|s|begin|origin|initial|start_node|start_vertex|source_node|from_node|root|node|vertex|v0|u)$|start|source|src|begin|origin", re.I)
GOAL_P = re.compile(r"^(goal|end|target|dest|destination|t|finish|to|stop|goal_node|end_node|target_node|dst|end_vertex|target_vertex)$|goal|end|target|dest|finish", re.I)
N_P = re.compile(r"^(n|num_nodes|num_vertices|v|vertices|size|num|nodes_count|n_nodes|node_count|num_v|V)$", re.I)
HEUR_P = re.compile(r"heur|^h$|estimate", re.I)
LIST_P = re.compile(r"^(arr|lst|list|nums|array|data|a|items|seq|values|elements|numbers|l|x|xs|input_list|my_list|alist|unsorted|collection|arr_)", re.I)
LOWHIGH_P = re.compile(r"^(low|lo|left|l|start|begin|first|p)$", re.I)
HIGH_P = re.compile(r"^(high|hi|right|r|end|last|q)$", re.I)
SKIP_FN = re.compile(r"^(main|print|display|show|reconstruct|heuristic|get_neighbou?rs?|neighbou?rs?|is_valid|valid|example|usage|demo|draw|read|parse|generate|random|test|swap|merge|partition|heapify|sift|_)", re.I)
NAME_SCORE = re.compile(r"path|search|bfs|dfs|dijkstra|astar|a_star|shortest|find|sort|solve|route|traverse|best|greedy|bellman|floyd|spfa|uniform|ucs|ida|iddfs|bidirectional|run", re.I)


def load_defs(code):
    tree = ast.parse(code)
    user_fns = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    keep = []
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            keep.append(n)
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            bad = False
            for c in ast.walk(n):
                if isinstance(c, ast.Call):
                    f = c.func
                    nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
                    if nm in user_fns or nm in ("input", "print", "open", "exit", "quit"):
                        bad = True
            if not bad:
                keep.append(n)
    mod = ast.Module(body=keep, type_ignores=[])
    ns = {"__name__": "candidate", "__builtins__": __builtins__}
    signal.setitimer(signal.ITIMER_REAL, 12.0)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            exec(compile(mod, "candidate", "exec"), ns)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    return ns, [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]


# ----------------------------------------------------------------------------
# graph representations
# ----------------------------------------------------------------------------
def graph_forms(inst, weighted, node_fn):
    n = inst["n"]
    edges = inst["edges"]  # undirected (u, v, w)
    nodes = [node_fn(i) for i in range(n)]
    dl, dd, dt = {x: [] for x in nodes}, {x: {} for x in nodes}, {x: [] for x in nodes}
    mat = [[0] * n for _ in range(n)]
    el = []
    for u, v, w in edges:
        a, b = node_fn(u), node_fn(v)
        dl[a].append(b); dl[b].append(a)
        dd[a][b] = w; dd[b][a] = w
        dt[a].append((b, w)); dt[b].append((a, w))
        mat[u][v] = w; mat[v][u] = w
        el.append((a, b, w) if weighted else (a, b))
        el.append((b, a, w) if weighted else (b, a))
    forms = {}
    if weighted:
        forms["dict_dict"] = dd
        forms["dict_tuples"] = dt
        forms["matrix"] = mat
        forms["edges"] = el
    else:
        forms["dict_list"] = dl
        forms["dict_dict"] = dd
        forms["matrix"] = mat
        forms["edges"] = el
        forms["dict_tuples"] = dt
        forms["edges_w"] = [(a, b, 1) for a, b in el]
    return forms


def is_none_like(o):
    if o is None or o is False:
        return True
    if isinstance(o, (list, tuple, str, dict, set)) and len(o) == 0:
        return True
    if isinstance(o, (int, float)) and not isinstance(o, bool) and (o == -1 or (isinstance(o, float) and math.isinf(o))):
        return True
    return False


def interpret_path_output(o, s, t, nodes):
    """Return dict(kind, path, dist, reach) or None if not well-formed."""
    nodeset = set(nodes)
    if o is True:
        return {"kind": "bool", "reach": True}
    if is_none_like(o):
        return {"kind": "none", "reach": False}
    if isinstance(o, (int, float)) and not isinstance(o, bool):
        return {"kind": "dist", "dist": float(o), "reach": True}
    if isinstance(o, dict) and s in o and isinstance(o[s], dict) and t in o[s] and isinstance(o[s][t], (int, float)):
        v = float(o[s][t]); return {"kind": "distdict", "dist": v, "reach": not math.isinf(v)}
    if isinstance(o, list) and o and all(isinstance(r, list) for r in o) and len(o) == len(nodes) \
            and isinstance(s, int) and all(len(r) == len(nodes) for r in o):
        try:
            v = float(o[s][t]); return {"kind": "distdict", "dist": v, "reach": not math.isinf(v)}
        except (TypeError, ValueError):
            return None
    if isinstance(o, dict):
        if t in o:
            val = o[t]
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                return {"kind": "distdict", "dist": float(val), "reach": not math.isinf(float(val))}
            if val in nodeset or val is None:
                # predecessor map -> reconstruct
                path = [t]
                cur = t
                for _ in range(len(nodes) + 2):
                    if cur == s:
                        break
                    cur = o.get(cur)
                    if cur is None:
                        return {"kind": "pred", "reach": False, "path": None}
                    path.append(cur)
                return {"kind": "pred", "path": path[::-1], "reach": path[-1] == s}
            return None
        return {"kind": "distdict", "dist": math.inf, "reach": False}
    if isinstance(o, (list, tuple)):
        lst = list(o)
        # (path, cost) or (cost, path)
        if len(lst) == 2 and isinstance(lst[0], (list, tuple)) and isinstance(lst[1], (int, float)):
            r = interpret_path_output(lst[0], s, t, nodes)
            if r is None:
                return None
            r["dist"] = float(lst[1]); return r
        if len(lst) == 2 and isinstance(lst[1], (list, tuple)) and isinstance(lst[0], (int, float)) and not isinstance(lst[0], bool):
            if math.isinf(float(lst[0])) or len(lst[1]) == 0:
                return {"kind": "none", "reach": False}
            r = interpret_path_output(lst[1], s, t, nodes)
            if r is None:
                return None
            r["dist"] = float(lst[0]); return r
        if len(lst) == 2 and isinstance(lst[0], dict) and isinstance(lst[1], dict):
            return interpret_path_output(lst[0], s, t, nodes)
        if len(lst) == 2 and lst[0] is None:
            return {"kind": "none", "reach": False}
        # path of nodes (allow tuples for grids)
        norm = [tuple(x) if isinstance(x, list) else x for x in lst]
        try:
            if all(x in nodeset for x in norm):
                return {"kind": "path", "path": norm, "reach": True}
        except TypeError:
            return None
        return None
    return None


def check_path(path, s, t, adj):
    if not path or path[0] != s or path[-1] != t:
        return False
    for a, b in zip(path, path[1:]):
        if b not in adj.get(a, {}):
            return False
    return True


def path_cost(path, adj):
    return sum(adj[a][b] for a, b in zip(path, path[1:]))


def eval_path_instance(interp, inst, s, t, adj, weighted):
    """Return (correct, optimal)."""
    reach = inst["reachable"]
    exp = inst["expected"]
    if interp is None:
        return False, False
    if not reach:
        ok = (interp["kind"] in ("none",)) or (interp.get("reach") is False) or \
             (interp["kind"] in ("dist", "distdict") and math.isinf(interp.get("dist", 0)))
        return ok, ok
    k = interp["kind"]
    if k in ("path", "pred"):
        p = interp.get("path")
        if p is None or not check_path(p, s, t, adj):
            return False, False
        c = path_cost(p, adj) if weighted else len(p) - 1
        if weighted:
            return abs(c - exp) < 1e-6, abs(c - exp) < 1e-6
        return True, c == exp
    if k in ("dist", "distdict"):
        d = interp.get("dist")
        ok = d is not None and abs(d - exp) < 1e-6
        return ok, ok
    if k == "bool":
        return (not weighted), False
    return False, False


def grid_adj(grid, diag):
    R, C = len(grid), len(grid[0])
    adj = {}
    for r in range(R):
        for c in range(C):
            if grid[r][c] == 1:
                continue
            nb = {}
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if (dr, dc) == (0, 0):
                        continue
                    if not diag and dr != 0 and dc != 0:
                        continue
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < R and 0 <= cc < C and grid[rr][cc] == 0:
                        nb[(rr, cc)] = 1
            adj[(r, c)] = nb
    return adj


# ----------------------------------------------------------------------------
# callable discovery and adapters
# ----------------------------------------------------------------------------
def candidate_callables(ns, order):
    cands = []
    for name in order:
        obj = ns.get(name)
        if obj is None:
            continue
        if inspect.isclass(obj):
            cands.append(("class", name, obj))
        elif callable(obj) and not SKIP_FN.match(name):
            cands.append(("func", name, obj))
    # helpers last-resort (e.g. a merge_sort named merge_sort passes SKIP? 'merge' prefix)
    for name in order:
        obj = ns.get(name)
        if obj is not None and callable(obj) and not inspect.isclass(obj) and SKIP_FN.match(name) \
                and re.search(r"sort|search|path", name, re.I):
            cands.append(("func", name, obj))
    cands.sort(key=lambda c: 0 if NAME_SCORE.search(c[1]) else 1)
    return cands


def required_params(fn):
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return None
    ps = []
    for p in sig.parameters.values():
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        ps.append((p.name, p.default is not p.empty))
    return ps


def call_with_timeout(fn, args, sec):
    signal.setitimer(signal.ITIMER_REAL, sec)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return fn(*args)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def path_arg_builders(params, weighted):
    """Yield (adapter_name, builder(form_dict, s, t, n, heur) -> args)."""
    names = [p for p, d in params]
    req = [p for p, d in params if not d]
    builders = []
    form_order = ["dict_dict", "dict_tuples", "dict_list", "matrix", "edges"] if weighted else \
        ["dict_list", "dict_dict", "matrix", "edges", "dict_tuples", "edges_w"]

    def mk(form, use):
        def b(F, s, t, n, heur):
            out = []
            for p in use:
                role = p[1]
                if role == "graph":
                    out.append(F[form])
                elif role == "edges":
                    out.append(F[form] if form.startswith("edges") else F["edges"])
                elif role == "s":
                    out.append(s)
                elif role == "t":
                    out.append(t)
                elif role == "n":
                    out.append(n)
                elif role == "h":
                    out.append(heur)
            return out
        return b

    # role assignment by name
    roles = []
    seen_s = seen_t = False
    for p, d in params:
        if HEUR_P.search(p):
            roles.append((p, "h", d))
        elif re.search(r"edge", p, re.I):
            roles.append((p, "edges", d))
        elif GRAPH_P.search(p) and not N_P.match(p):
            roles.append((p, "graph", d))
        elif N_P.match(p):
            roles.append((p, "n", d))
        elif GOAL_P.search(p) and not seen_t:
            roles.append((p, "t", d)); seen_t = True
        elif START_P.search(p) and not seen_s:
            roles.append((p, "s", d)); seen_s = True
        else:
            roles.append((p, "?", d))
    use = [r for r in roles if not r[2] or r[1] in ("s", "t", "h")]
    if all(r[1] != "?" for r in use) and any(r[1] in ("graph", "edges") for r in use):
        for f in form_order:
            builders.append((f"named:{f}", mk(f, [(r[0], r[1]) for r in use])))
    # positional fallbacks over required params
    k = len(req)
    for f in form_order:
        if k == 1:
            builders.append((f"pos1:{f}", mk(f, [("a", "graph")])))
        if k == 3:
            builders.append((f"pos3:{f}", mk(f, [("a", "graph"), ("b", "s"), ("c", "t")])))
        elif k == 2:
            builders.append((f"pos2:{f}", mk(f, [("a", "graph"), ("b", "s")])))
        elif k == 4:
            builders.append((f"pos4:{f}", mk(f, [("a", "graph"), ("b", "s"), ("c", "t"), ("d", "h")])))
            builders.append((f"pos4n:{f}", mk(f, [("a", "n"), ("b", "edges"), ("c", "s"), ("d", "t")])))
    return builders


def run_path_task(ns, order, job):
    weighted = job["task"] == "T3"
    insts = job["instances"]
    grid_insts = job.get("grid_instances", [])
    smoke = insts[0]
    node_fns = [("int", lambda i: i), ("str", lambda i: chr(65 + i) if i < 26 else "N%d" % i)]
    cands = candidate_callables(ns, order)
    zero_h = lambda a, b: 0  # admissible

    def manhattan(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    # --- graph adapters
    for kind, name, obj in cands:
        attempts = []
        if kind == "func":
            params = required_params(obj)
            if params is None:
                continue
            for nf_name, nf in node_fns:
                for ad, b in path_arg_builders(params, weighted):
                    attempts.append((f"{name}|{nf_name}|{ad}", nf, (lambda b=b, obj=obj: (lambda F, s, t, n, h: obj(*b(F, s, t, n, h))))()))
            # grid adapter
            if not weighted and grid_insts:
                ps = [p for p, d in params if not d]
                if len(ps) in (3, 4):
                    def gcall(g, s, t, obj=obj, k=len(ps)):
                        return obj(g, s, t) if k == 3 else obj(g, s, t, manhattan)
                    attempts.append((f"{name}|grid", None, gcall))
        else:
            cls = obj
            methods = [m for m in dir(cls) if not m.startswith("_") and callable(getattr(cls, m, None))]
            add_m = [m for m in methods if re.search(r"add_?edge|addedge|connect|add$", m, re.I)]
            search_m = [m for m in methods if NAME_SCORE.search(m) and m not in add_m]
            for nf_name, nf in node_fns:
                for ctor in ("empty", "n", "graph_dd", "graph_dl", "graph_dt"):
                    for sm in search_m:
                        def ccall(F, s, t, n, h, cls=cls, ctor=ctor, sm=sm, add_m=add_m):
                            if ctor == "empty":
                                inst = cls()
                            elif ctor == "n":
                                inst = cls(n)
                            elif ctor == "graph_dd":
                                inst = cls(F["dict_dict"])
                            elif ctor == "graph_dl":
                                inst = cls(F.get("dict_list", F["dict_tuples"]))
                            else:
                                inst = cls(F["dict_tuples"])
                            if ctor in ("empty", "n"):
                                if not add_m:
                                    raise TypeError("no add_edge")
                                am = getattr(inst, add_m[0])
                                k = len([p for p, d in (required_params(am) or []) if not d])
                                for e in F["edges"]:
                                    am(*e[:k]) if k <= len(e) else am(*e)
                            meth = getattr(inst, sm)
                            k = len([p for p, d in (required_params(meth) or []) if not d])
                            if k == 2:
                                return meth(s, t)
                            if k == 1:
                                return meth(s)
                            if k == 3:
                                return meth(s, t, h)
                            return meth()
                        attempts.append((f"{cls.__name__}.{sm}|{nf_name}|{ctor}", nf, ccall))
        for adname, nf, fn in attempts:
            if adname.endswith("|grid"):
                if not grid_insts:
                    continue
                gi = grid_insts[0]
                g = [row[:] for row in gi["grid"]]
                s, t = tuple(gi["s"]), tuple(gi["t"])
                try:
                    o = call_with_timeout(fn, (g, s, t), 1.0)
                except BaseException:
                    continue
                nodes = list(grid_adj(gi["grid"], True).keys())
                if interpret_path_output(o, s, t, nodes) is None:
                    continue
                return evaluate_grid(fn, grid_insts, adname)
            F = graph_forms(smoke, weighted, nf)
            nodes = [nf(i) for i in range(smoke["n"])]
            try:
                o = call_with_timeout(fn, (F, nf(smoke["s"]), nf(smoke["t"]), smoke["n"], zero_h), 1.0)
            except BaseException:
                continue
            it = interpret_path_output(o, nf(smoke["s"]), nf(smoke["t"]), nodes)
            if it is None or it["kind"] == "none":
                continue
            if it["kind"] == "path" and not check_path(it["path"], nf(smoke["s"]), nf(smoke["t"]), F["dict_dict"]):
                continue
            return evaluate_graph(fn, insts, nf, weighted, adname)
    return {"exec_status": "not_callable", "pass_rate": 0.0, "adapter": None}


def evaluate_graph(fn, insts, nf, weighted, adname):
    n_ok = n_opt = 0
    n_timeout = 0
    for inst in insts:
        F = graph_forms(inst, weighted, nf)
        s, t = nf(inst["s"]), nf(inst["t"])
        nodes = [nf(i) for i in range(inst["n"])]
        try:
            o = call_with_timeout(fn, (F, s, t, inst["n"], lambda a, b: 0), 0.5)
            it = interpret_path_output(o, s, t, nodes)
        except _Timeout:
            n_timeout += 1
            it = None
        except BaseException:
            it = None
        ok, opt = eval_path_instance(it, inst, s, t, F["dict_dict"], weighted)
        n_ok += ok; n_opt += opt
    pr = n_ok / len(insts)
    return {"exec_status": "pass" if pr == 1.0 else "fail", "pass_rate": pr, "optimal_rate": n_opt / len(insts),
            "adapter": adname, "n_instance_timeouts": n_timeout}


def evaluate_grid(fn, ginsts, adname):
    n_ok = n_opt = n_timeout = 0
    for gi in ginsts:
        g = [row[:] for row in gi["grid"]]
        s, t = tuple(gi["s"]), tuple(gi["t"])
        adj4 = grid_adj(gi["grid"], False)
        adj8 = grid_adj(gi["grid"], True)
        try:
            o = call_with_timeout(fn, (g, s, t), 0.5)
            it = interpret_path_output(o, s, t, list(adj8.keys()))
        except _Timeout:
            n_timeout += 1; it = None
        except BaseException:
            it = None
        ok4, opt4 = eval_path_instance(it, {"reachable": gi["reachable"], "expected": gi["expected"]}, s, t, adj4, False)
        ok8, _ = eval_path_instance(it, {"reachable": gi["reachable8"], "expected": gi["expected8"]}, s, t, adj8, False)
        n_ok += (ok4 or ok8); n_opt += opt4
    pr = n_ok / len(ginsts)
    return {"exec_status": "pass" if pr == 1.0 else "fail", "pass_rate": pr, "optimal_rate": n_opt / len(ginsts),
            "adapter": adname, "n_instance_timeouts": n_timeout}


def run_sort_task(ns, order, job):
    insts = job["instances"]
    cands = candidate_callables(ns, order)
    smoke = [5, 3, 9, 1, 1, 0, 7]
    for kind, name, obj in cands:
        attempts = []
        if kind == "func":
            params = required_params(obj)
            if params is None:
                continue
            req = [p for p, d in params if not d]
            if len(req) == 1:
                attempts.append((f"{name}|list", lambda a, obj=obj: obj(a)))
            elif len(req) == 3:
                attempts.append((f"{name}|list_lo_hi", lambda a, obj=obj: obj(a, 0, len(a) - 1)))
                attempts.append((f"{name}|list_lo_len", lambda a, obj=obj: obj(a, 0, len(a))))
            elif len(req) == 2:
                attempts.append((f"{name}|list_n", lambda a, obj=obj: obj(a, len(a))))
            elif len(req) == 0:
                attempts.append((f"{name}|kw", lambda a, obj=obj: obj(a)))
        else:
            methods = [m for m in dir(obj) if not m.startswith("_") and re.search(r"sort", m, re.I)]
            for m in methods:
                attempts.append((f"{obj.__name__}.{m}|ctor_list", lambda a, obj=obj, m=m: getattr(obj(a), m)()))
                attempts.append((f"{obj.__name__}.{m}|ctor_empty", lambda a, obj=obj, m=m: getattr(obj(), m)(a)))
        for adname, fn in attempts:
            a = list(smoke)
            try:
                o = call_with_timeout(fn, (a,), 1.0)
            except BaseException:
                continue
            res = o if isinstance(o, list) else (list(o) if isinstance(o, tuple) else (a if o is None else None))
            if res is None or len(res) != len(smoke):
                continue
            if res != sorted(smoke) and res != sorted([x for x in smoke if x >= 0]):
                # accept also partially-correct (e.g., negative handling bug) as well-formed if sorted-ish
                if sorted(res) != sorted(smoke):
                    continue
            n_ok = n_ok_nn = n_nn = 0
            n_timeout = 0
            for lst in insts:
                a = list(lst)
                try:
                    o = call_with_timeout(fn, (a,), 0.5)
                    res = o if isinstance(o, list) else (list(o) if isinstance(o, tuple) else (a if o is None else None))
                    ok = res == sorted(lst)
                except _Timeout:
                    n_timeout += 1; ok = False
                except BaseException:
                    ok = False
                n_ok += ok
                if all(isinstance(x, int) and x >= 0 for x in lst):
                    n_nn += 1; n_ok_nn += ok
            pr = n_ok / len(insts)
            return {"exec_status": "pass" if pr == 1.0 else "fail", "pass_rate": pr,
                    "pass_rate_nonneg_int": (n_ok_nn / n_nn) if n_nn else None, "adapter": adname,
                    "n_instance_timeouts": n_timeout}
    return {"exec_status": "not_callable", "pass_rate": 0.0, "adapter": None}


def main():
    job = json.load(open(sys.argv[1]))
    lim = int(job.get("mem_bytes", 2 * 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_AS, (lim, lim))
    cpu = int(job.get("cpu_sec", 30))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    sys.setrecursionlimit(5000)
    try:
        ns, order = load_defs(job["code"])
    except BaseException as e:  # noqa: BLE001 - sandbox boundary
        print(json.dumps({"exec_status": "import_fail", "pass_rate": 0.0, "adapter": None, "error": repr(e)[:200]}))
        return
    try:
        if job["task"] == "T2":
            r = run_sort_task(ns, order, job)
        else:
            r = run_path_task(ns, order, job)
    except BaseException as e:  # noqa: BLE001
        r = {"exec_status": "fail", "pass_rate": 0.0, "adapter": None, "error": repr(e)[:200]}
    sys.stdout = sys.__stdout__
    print(json.dumps(r))


if __name__ == "__main__":
    main()
