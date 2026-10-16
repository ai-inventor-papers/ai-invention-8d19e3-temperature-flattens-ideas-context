"""Sandboxed execution harness (run as: python -I oracle_harness.py <code_file> <task> <result_file>).

Discovers an entry point + calling convention on the first test, then runs all tests with it.
Graph tests use a stdlib reference Dijkstra/BFS (equivalent to networkx dijkstra_path_length).
"""
import builtins
import heapq
import inspect
import io
import json
import math
import random
import re
import resource
import signal
import sys
import types
from collections import deque

CODE_FILE, TASK, RESULT_FILE = sys.argv[1], sys.argv[2], sys.argv[3]
resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
sys.setrecursionlimit(5000)


class TimeoutErr(Exception):
    pass


def _alarm(signum, frame):
    raise TimeoutErr()


signal.signal(signal.SIGALRM, _alarm)


def call_with_timeout(fn, args, secs=1.0):
    signal.setitimer(signal.ITIMER_REAL, secs)
    try:
        return fn(*args)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def write_result(d):
    with open(RESULT_FILE, "w") as fh:
        json.dump(d, fh)


# ------------------------------------------------------------------ load program (stdout muted, input() disabled)
def _no_input(*a, **k):
    raise EOFError("input disabled")


builtins.input = _no_input
_real_stdout = sys.stdout
sys.stdout = io.StringIO()
mod = types.ModuleType("prog")
mod.__dict__["__name__"] = "prog"
src = open(CODE_FILE).read()
try:
    signal.setitimer(signal.ITIMER_REAL, 3.0)
    exec(compile(src, "prog.py", "exec"), mod.__dict__)
    signal.setitimer(signal.ITIMER_REAL, 0)
except BaseException as e:  # noqa: BLE001  - program crashed at import; may still have defined functions
    signal.setitimer(signal.ITIMER_REAL, 0)
    load_err = repr(e)[:200]
else:
    load_err = None

# ------------------------------------------------------------------ test generation
INF = float("inf")


def gen_graph(seed, weighted, reachable=True):
    rng = random.Random(seed)
    n = rng.randint(6, 40)
    adj = {u: {} for u in range(n)}
    for u in range(n):
        for v in range(u + 1, n):
            if rng.random() < 0.15:
                w = rng.randint(1, 20) if weighted else 1
                adj[u][v] = w
                adj[v][u] = w
    s, t = rng.sample(range(n), 2)
    if reachable:
        mids = rng.sample([x for x in range(n) if x not in (s, t)], rng.randint(1, min(5, n - 2)))
        chain = [s] + mids + [t]
        for a, b in zip(chain, chain[1:]):
            if b not in adj[a]:
                w = rng.randint(1, 20) if weighted else 1
                adj[a][b] = w
                adj[b][a] = w
    else:
        for v in list(adj[t]):
            del adj[v][t]
        adj[t] = {}
    return n, adj, s, t


def ref_dist(adj, s, t):
    dist = {s: 0}
    pq = [(0, s)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, INF):
            continue
        for v, w in adj[u].items():
            if d + w < dist.get(v, INF):
                dist[v] = d + w
                heapq.heappush(pq, (d + w, v))
    return dist.get(t, INF)


def gen_grid(seed):
    rng = random.Random(1000 + seed)
    r, c = rng.randint(5, 12), rng.randint(5, 12)
    g = [[1 if rng.random() < 0.25 else 0 for _ in range(c)] for _ in range(r)]
    s = (0, 0)
    t = (r - 1, c - 1)
    if seed % 5 != 4:  # carve guaranteed path
        x, y = 0, 0
        g[0][0] = 0
        while (x, y) != t:
            if x < r - 1 and (y == c - 1 or rng.random() < 0.5):
                x += 1
            else:
                y += 1
            g[x][y] = 0
    else:  # unreachable: wall around goal
        g[t[0]][t[1]] = 0
        g[t[0] - 1][t[1]] = 1
        g[t[0]][t[1] - 1] = 1
        g[t[0] - 1][t[1] - 1] = 1
        g[0][0] = 0
    adj = {}
    for i in range(r):
        for j in range(c):
            if g[i][j] == 0:
                adj[(i, j)] = {}
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    a, b = i + di, j + dj
                    if 0 <= a < r and 0 <= b < c and g[a][b] == 0:
                        adj[(i, j)][(a, b)] = 1
    return g, adj, s, t


def fmt_graph(fmt, n, adj):
    if fmt == "adjlist":
        return {u: list(vs.keys()) for u, vs in adj.items()}
    if fmt == "dictdict":
        return {u: dict(vs) for u, vs in adj.items()}
    if fmt == "dicttuple":
        return {u: [(v, w) for v, w in vs.items()] for u, vs in adj.items()}
    if fmt == "dictstr":
        return {str(u): {str(v): w for v, w in vs.items()} for u, vs in adj.items()}
    if fmt == "matrix0":
        return [[adj[i].get(j, 0) for j in range(n)] for i in range(n)]
    if fmt == "matrixinf":
        return [[0 if i == j else adj[i].get(j, INF) for j in range(n)] for i in range(n)]
    raise ValueError(fmt)


# ------------------------------------------------------------------ result interpretation
def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def norm_node(x, fmt):
    if fmt == "dictstr" and isinstance(x, str) and x.lstrip("-").isdigit():
        return int(x)
    return x


def parse_ret(ret, t, fmt):
    """Return (path or None, cost or None, unreachable_flag)."""
    if ret is None or ret is False:
        return None, None, True
    if isinstance(ret, (list, tuple)) and len(ret) == 0:
        return None, None, True
    if is_num(ret):
        return None, ret, ret == INF or ret == -1
    if ret is True:
        return None, None, False
    if isinstance(ret, dict):
        key = str(t) if fmt == "dictstr" else t
        if key in ret and (is_num(ret[key]) or ret[key] is None):
            v = ret[key]
            return None, v, v is None or v == INF
        if key not in ret and all(is_num(v) for v in ret.values()) and ret:
            return None, None, True
        return None, None, None
    if isinstance(ret, (list, tuple)):
        if len(ret) == 2:
            a, b = ret
            if is_num(a) and (isinstance(b, (list, tuple)) or b is None):
                return (list(b) if b else None), a, (not b) or a == INF
            if is_num(b) and (isinstance(a, (list, tuple)) or a is None):
                return (list(a) if a else None), b, (not a) or b == INF
            if isinstance(a, dict) and isinstance(b, dict):  # (dist, prev)
                return parse_ret(a, t, fmt)
            if isinstance(a, dict):
                return parse_ret(a, t, fmt)
            if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) and is_num(a[0]) and \
                    not isinstance(a[0], tuple) and len(a) > 2:
                pass
        if all(is_num(x) for x in ret) and len(ret) > 2 and fmt.startswith("matrix"):
            # dist list indexed by node
            return None, (ret[t] if t < len(ret) else None), False
        return [norm_node(x, fmt) if not isinstance(x, list) else tuple(x) for x in ret], None, False
    return None, None, None


def path_cost(adj, path):
    c = 0
    for a, b in zip(path, path[1:]):
        if b not in adj.get(a, {}):
            return None
        c += adj[a][b]
    return c


def eval_graph(ret, adj, s, t, fmt, weighted):
    """Return (pass, shortest)."""
    true = ref_dist(adj, s, t)
    path, cost, unreach = parse_ret(ret, t, fmt)
    if true == INF:
        ok = bool(unreach) or (path is None and cost is None and ret in (None, [], False, ()))
        return ok, ok
    if unreach:
        return False, False
    if path is not None:
        path = [tuple(p) if isinstance(p, list) else p for p in path]
        if not path or path[0] != s or path[-1] != t:
            return False, False
        pc = path_cost(adj, path)
        if pc is None:
            return False, False
        if cost is not None and abs(cost - pc) > 1e-6 and abs(cost - true) > 1e-6:
            return False, False
        shortest = abs(pc - true) < 1e-6
        return (shortest if weighted else True), shortest
    if cost is not None:
        ok = abs(cost - true) < 1e-6
        return (ok if weighted else ok), ok
    if ret is True:
        return (not weighted), False
    return False, False


# ------------------------------------------------------------------ entry point discovery
NAME_HINT = re.compile(r"search|path|bfs|dfs|dijkstra|a_?star|find|shortest|route|solve|traverse|bellman|spfa|"
                       r"floyd|iddfs|sort", re.I)
SKIP = re.compile(r"^(reconstruct\w*|heuristic\w*|h|print\w*|main|_?test\w*|neighbors?|get_neighbors?|"
                  r"is_valid\w*|manhattan\w*|euclid\w*|swap|merge|partition|heapify|display\w*|add_edge)$", re.I)
G_P = re.compile(r"graph|adj|edges?|grid|maze|matrix|^g$|nodes|network|weights?|board|map", re.I)
S_P = re.compile(r"start|src|source|^s$|begin|origin|initial|^u$|from", re.I)
T_P = re.compile(r"goal|target|end|dest|^t$|finish|^v$|^to$|stop", re.I)


def callables():
    out = []
    for name, obj in list(mod.__dict__.items()):
        if name.startswith("__") or SKIP.match(name):
            continue
        if inspect.isfunction(obj) and obj.__module__ in (None, "prog", "builtins") or (
                inspect.isfunction(obj) and getattr(obj, "__code__", None) and obj.__code__.co_filename == "prog.py"):
            out.append(("func", name, obj))
        elif inspect.isclass(obj) and getattr(obj, "__module__", "") in ("prog",):
            out.append(("class", name, obj))
    called = set()
    for _, _, obj in out:
        code = getattr(obj, "__code__", None)
        if code is not None:
            called |= {n for n in code.co_names if n != obj.__name__}
    # entry points (not called by other program functions) first, then name hints
    out.sort(key=lambda x: (x[1] in called, 0 if NAME_HINT.search(x[1]) else 1, x[0] != "func"))
    return out


def req_params(fn):
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return None, None, []
    ps = [p for p in sig.parameters.values() if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    req = [p for p in ps if p.default is p.empty]
    return len(req), len(ps), [p.name for p in ps]


def arg_orders(names, nmin, nmax):
    """Candidate argument tuples (as symbolic 'G','S','T') ordered: name-matched first."""
    cands = []
    if names and nmin is not None:
        sym = []
        for nm in names[:3]:
            sym.append("G" if G_P.search(nm) else "S" if S_P.search(nm) else "T" if T_P.search(nm) else "?")
        if "?" not in sym and len(set(sym)) == len(sym) and nmin <= len(sym):
            cands.append(tuple(sym))
    for c in [("G", "S", "T"), ("G", "S"), ("S", "T", "G"), ("S", "G", "T")]:
        if c not in cands and nmin is not None and nmin <= len(c) <= nmax:
            cands.append(c)
    return cands


def method_targets(obj):
    ms = []
    for nm, m in inspect.getmembers(obj, predicate=inspect.ismethod):
        if nm.startswith("_") or SKIP.match(nm):
            continue
        ms.append((nm, m))
    ms.sort(key=lambda x: 0 if NAME_HINT.search(x[0]) else 1)
    return ms


def build_instances(cls, gobj, n, adj, fmt):
    """Yield instance candidates."""
    for ctor in ("graph", "empty_addedge", "n_addedge"):
        try:
            if ctor == "graph":
                inst = call_with_timeout(cls, (gobj,))
            else:
                inst = call_with_timeout(cls, () if ctor == "empty_addedge" else (n,))
                add = None
                for nm in ("add_edge", "addEdge", "add_edges", "connect"):
                    if hasattr(inst, nm):
                        add = getattr(inst, nm)
                        break
                if add is None:
                    continue
                k = req_params(add)[1] or 0
                for u, vs in adj.items():
                    for v, w in vs.items():
                        if k >= 3:
                            call_with_timeout(add, (u, v, w))
                        else:
                            call_with_timeout(add, (u, v))
            yield ctor, inst
        except BaseException:  # noqa: BLE001
            continue


def graph_tests():
    weighted = TASK == "T3"
    tests = []
    for i in range(50):
        n, adj, s, t = gen_graph(i, weighted, reachable=(i % 10 != 9))
        tests.append(("graph", n, adj, s, t))
    grids = []
    if TASK == "T1":
        for i in range(25):
            g, adj, s, t = gen_grid(i)
            grids.append(("grid", g, adj, s, t))
    return tests, grids, weighted


def run_graph():
    tests, grids, weighted = graph_tests()
    fmts = (["adjlist", "dictdict", "dicttuple", "matrix0", "matrixinf", "dictstr"] if not weighted
            else ["dictdict", "dicttuple", "matrix0", "matrixinf", "dictstr", "adjlist"])
    cands = callables()
    any_callable = False

    def mk_args(order, gobj, s, t, fmt):
        if fmt == "dictstr":
            s, t = str(s), str(t)
        m = {"G": gobj, "S": s, "T": t}
        return tuple(m[x] for x in order)

    def try_suite(suite, invoke):
        npass = nshort = 0
        for k, (_, a, adj, s, t) in enumerate(suite):
            try:
                ret = invoke(a, adj, s, t)
                ok, sh = eval_graph(ret, adj, s, t, cur_fmt, weighted)
            except BaseException:  # noqa: BLE001
                ok, sh = False, False
            npass += ok
            nshort += sh
        return npass, nshort

    # convention discovery on first reachable test of each suite
    for suite_name, suite, fmt_list in (("graph", tests, fmts), ("grid", grids, ["grid"])):
        if not suite:
            continue
        _, a0, adj0, s0, t0 = suite[0]
        for kind, name, obj in cands:
            for fmt in fmt_list:
                cur_fmt = fmt if fmt != "grid" else "grid"
                g0 = a0 if fmt == "grid" else fmt_graph(fmt, a0, adj0)
                if kind == "func":
                    nmin, nmax, names = req_params(obj)
                    if nmin is None:
                        continue
                    for order in arg_orders(names, nmin, nmax):
                        try:
                            ret = call_with_timeout(obj, mk_args(order, g0, s0, t0, cur_fmt))
                            any_callable = True
                            ok, _ = eval_graph(ret, adj0, s0, t0, cur_fmt, weighted)
                        except BaseException:  # noqa: BLE001
                            continue
                        if ok:
                            def invoke(a, adj, s, t, obj=obj, order=order, fmt=fmt):
                                gg = a if fmt == "grid" else fmt_graph(fmt, a, adj)
                                return call_with_timeout(obj, mk_args(order, gg, s, t, fmt))
                            globals()["cur_fmt"] = cur_fmt
                            npass, nshort = try_suite(suite, invoke)
                            return dict(callable=True, convention=f"{name}:{fmt}:{''.join(order)}",
                                        n_tests=len(suite), n_pass=npass, pass_frac=npass / len(suite),
                                        shortest_rate=nshort / len(suite), passed=npass == len(suite))
                else:
                    for ctor, inst in build_instances(obj, g0, a0 if isinstance(a0, int) else 0, adj0, fmt):
                        for mname, meth in method_targets(inst):
                            nmin, nmax, names = req_params(meth)
                            if nmin is None:
                                continue
                            for order in [("S", "T"), ("S",), ("G", "S", "T")]:
                                if not (nmin <= len(order) <= nmax):
                                    continue
                                try:
                                    ret = call_with_timeout(meth, mk_args(order, g0, s0, t0, cur_fmt))
                                    any_callable = True
                                    ok, _ = eval_graph(ret, adj0, s0, t0, cur_fmt, weighted)
                                except BaseException:  # noqa: BLE001
                                    continue
                                if ok:
                                    def invoke(a, adj, s, t, obj=obj, ctor=ctor, mname=mname, order=order, fmt=fmt):
                                        gg = a if fmt == "grid" else fmt_graph(fmt, a, adj)
                                        n_ = a if isinstance(a, int) else 0
                                        for c2, inst2 in build_instances(obj, gg, n_, adj, fmt):
                                            if c2 == ctor:
                                                return call_with_timeout(getattr(inst2, mname),
                                                                         mk_args(order, gg, s, t, fmt))
                                        raise RuntimeError("ctor failed")
                                    globals()["cur_fmt"] = cur_fmt
                                    npass, nshort = try_suite(suite, invoke)
                                    return dict(callable=True, convention=f"{name}.{mname}:{ctor}:{fmt}:{''.join(order)}",
                                                n_tests=len(suite), n_pass=npass, pass_frac=npass / len(suite),
                                                shortest_rate=nshort / len(suite), passed=npass == len(suite))
    return dict(callable=any_callable, convention=None, n_tests=0, n_pass=0, pass_frac=0.0, shortest_rate=0.0,
                passed=False)


def run_sort():
    rng = random.Random(0)
    tests = [[]] + [[rng.randint(-1000, 1000) for _ in range(rng.randint(1, 200))] for _ in range(48)] + \
        [[5, 5, 5, 1, 1, 2]]
    cands = callables()
    any_callable = False

    def invoke_with(fn, mode, arr):
        a = list(arr)
        if mode == "1":
            ret = call_with_timeout(fn, (a,))
        elif mode == "2n":
            ret = call_with_timeout(fn, (a, len(a)))
        else:
            ret = call_with_timeout(fn, (a, 0, len(a) - 1))
        if isinstance(ret, (list, tuple)):
            return list(ret)
        return a

    for kind, name, obj in cands:
        fns = []
        if kind == "func":
            fns.append((name, obj))
        else:
            try:
                inst = call_with_timeout(obj, ())
                fns += [(f"{name}.{m}", f) for m, f in method_targets(inst)]
            except BaseException:  # noqa: BLE001
                pass
            for arg in (list(tests[1]),):
                try:
                    inst = call_with_timeout(obj, (arg,))
                    fns += [(f"{name}(arr).{m}", f) for m, f in method_targets(inst)]
                except BaseException:  # noqa: BLE001
                    pass
        for fname, fn in fns:
            nmin, nmax, _ = req_params(fn)
            if nmin is None:
                continue
            for mode, k in (("1", 1), ("2n", 2), ("3lohi", 3)):
                if not (nmin <= k <= nmax):
                    continue
                probe = tests[1]
                try:
                    out = invoke_with(fn, mode, probe)
                    any_callable = True
                except BaseException:  # noqa: BLE001
                    continue
                if out == sorted(probe):
                    npass = 0
                    for arr in tests:
                        try:
                            npass += invoke_with(fn, mode, arr) == sorted(arr)
                        except BaseException:  # noqa: BLE001
                            pass
                    return dict(callable=True, convention=f"{fname}:{mode}", n_tests=len(tests), n_pass=npass,
                                pass_frac=npass / len(tests), shortest_rate=None, passed=npass == len(tests))
    return dict(callable=any_callable, convention=None, n_tests=0, n_pass=0, pass_frac=0.0, shortest_rate=None,
                passed=False)


cur_fmt = "adjlist"
try:
    res = run_sort() if TASK == "T2" else run_graph()
except BaseException as e:  # noqa: BLE001
    res = dict(callable=False, convention=None, n_tests=0, n_pass=0, pass_frac=0.0, shortest_rate=None,
               passed=False, error=repr(e)[:200])
res["load_error"] = load_err
write_result(res)
