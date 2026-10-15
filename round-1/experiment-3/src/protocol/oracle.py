"""Sandboxed execution oracle on 50 fixed random graphs (seed 12345), identical for every program.

Each program runs in its own `python -I` subprocess with RLIMIT_CPU=5 s and RLIMIT_AS=1 GB, a temp
cwd inside the workspace, stdin closed, and its stdout/stderr discarded. The harness writes one
result line per instance to a results file (flushed), so partial credit survives a kill.
"""

from __future__ import annotations

import heapq
import json
import math
import os
import random
import resource
import subprocess
import sys
import tempfile
from collections import deque
from pathlib import Path

N_GRAPHS = 50
GRAPH_SEED = 12345

HARNESS = r'''
import sys, json, copy, math, os, signal
sys.setrecursionlimit(5000)
code_path, inst_path, out_path, func = sys.argv[1:5]
insts = json.load(open(inst_path))
out = open(out_path, "w", buffering=1)
real_stdout = sys.stdout
sys.stdout = open(os.devnull, "w"); sys.stderr = open(os.devnull, "w")
ns = {"__name__": "__candidate__"}
try:
    exec(compile(open(code_path).read(), "candidate.py", "exec"), ns)
except BaseException as e:
    out.write(json.dumps({"load_error": type(e).__name__}) + "\n"); out.flush(); os._exit(0)
fn = ns.get(func)
if fn is None:
    out.write(json.dumps({"load_error": "missing_function"}) + "\n"); out.flush(); os._exit(0)
def enc(x):
    if isinstance(x, float) and math.isinf(x): return "INF"
    if isinstance(x, (list, tuple)): return [enc(v) for v in x]
    if isinstance(x, (int, float, str)) or x is None: return x
    try:
        return enc(list(x))
    except BaseException:
        return repr(x)[:200]
for i, inst in enumerate(insts):
    g = {int(k): ([tuple(e) for e in v] if inst["weighted"] else list(v)) for k, v in inst["graph"].items()}
    try:
        r = fn(copy.deepcopy(g), inst["s"], inst["t"])
        rec = {"i": i, "ok": True, "ret": enc(r), "is_tuple": isinstance(r, (tuple, list)), "none": r is None}
    except BaseException as e:
        rec = {"i": i, "ok": False, "err": type(e).__name__}
    out.write(json.dumps(rec) + "\n"); out.flush()
os._exit(0)
'''


def make_graphs(seed: int = GRAPH_SEED, n: int = N_GRAPHS) -> list[dict]:
    """50 directed graphs: 10-60 nodes, density 0.05-0.3, ~20% unreachable targets, edge cases."""
    rng = random.Random(seed)
    graphs = []
    for i in range(n):
        nn = rng.randint(10, 60)
        dens = rng.uniform(0.05, 0.3)
        adj: dict[int, list[tuple[int, float]]] = {u: [] for u in range(nn)}
        for u in range(nn):
            for v in range(nn):
                if u != v and rng.random() < dens:
                    w = rng.randint(1, 20) if i % 7 else round(rng.uniform(0.0, 10.0), 3)
                    adj[u].append((v, w))
        kind = "normal"
        s, t = rng.randrange(nn), rng.randrange(nn)
        if i in (0, 17, 33):  # start == goal
            t = s
            kind = "start_eq_goal"
        elif i in (5, 41):  # isolated goal node
            iso = nn - 1
            adj[iso] = []
            for u in adj:
                adj[u] = [(v, w) for v, w in adj[u] if v != iso]
            t = iso
            s = 0
            kind = "isolated_goal"
        elif i in (9, 27):  # self loops everywhere
            for u in adj:
                adj[u].append((u, rng.randint(1, 5)))
            kind = "self_loops"
        elif i % 5 == 3:  # force unreachable: cut every edge into a target set
            blocked = set(rng.sample(range(nn), max(2, nn // 4)))
            t = rng.choice(sorted(blocked))
            s = rng.choice([u for u in range(nn) if u not in blocked])
            for u in adj:
                if u not in blocked:
                    adj[u] = [(v, w) for v, w in adj[u] if v not in blocked]
            kind = "unreachable"
        while s == t and kind not in ("start_eq_goal",):
            t = rng.randrange(nn)
        graphs.append({"adj": {u: adj[u] for u in adj}, "s": s, "t": t, "kind": kind})
    return graphs


def ref_bfs(adj: dict, s: int, t: int) -> int | None:
    dist = {s: 0}
    q = deque([s])
    while q:
        u = q.popleft()
        if u == t:
            return dist[u]
        for v, _ in adj[u]:
            if v not in dist:
                dist[v] = dist[u] + 1
                q.append(v)
    return None


def ref_dijkstra(adj: dict, s: int, t: int) -> float:
    dist = {s: 0.0}
    pq = [(0.0, s)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, math.inf):
            continue
        if u == t:
            return d
        for v, w in adj[u]:
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                heapq.heappush(pq, (nd, v))
    return math.inf


def instances_for(task: str, graphs: list[dict]) -> list[dict]:
    out = []
    for g in graphs:
        if task == "T1":
            graph = {str(u): sorted({v for v, _ in es}) for u, es in g["adj"].items()}
        else:
            graph = {str(u): [[v, w] for v, w in es] for u, es in g["adj"].items()}
        out.append({"graph": graph, "s": g["s"], "t": g["t"], "weighted": task == "T3"})
    return out


class Oracle:
    def __init__(self, workdir: Path):
        self.graphs = make_graphs()
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.harness = self.workdir / "harness.py"
        self.harness.write_text(HARNESS)
        self.inst_paths = {}
        self.refs = {}
        for task in ("T1", "T3"):
            p = self.workdir / f"instances_{task}.json"
            p.write_text(json.dumps(instances_for(task, self.graphs)))
            self.inst_paths[task] = p
            self.refs[task] = [ref_bfs(g["adj"], g["s"], g["t"]) if task == "T1" else ref_dijkstra(g["adj"], g["s"], g["t"])
                               for g in self.graphs]

    def check(self, task: str, recs: list[dict]) -> dict:
        by_i = {r["i"]: r for r in recs if "i" in r}
        correct, shortest = [], []
        for i, g in enumerate(self.graphs):
            r = by_i.get(i)
            ok, sh = False, False
            if r is not None and r.get("ok"):
                ret = r["ret"]
                adj = g["adj"]
                edges = {(u, v): w for u, es in adj.items() for v, w in es}
                ref = self.refs[task][i]
                if task == "T1":
                    if ref is None:
                        ok = sh = ret is None
                    else:
                        try:  # malformed returns (e.g. nested lists -> unhashable) count as incorrect
                            valid = isinstance(ret, list) and ret and ret[0] == g["s"] and ret[-1] == g["t"] and all(
                                (ret[k], ret[k + 1]) in edges for k in range(len(ret) - 1))
                        except TypeError:
                            valid = False
                        if valid:
                            ok = True
                            sh = len(ret) - 1 == ref
                else:
                    if isinstance(ret, list) and len(ret) == 2:
                        d, p = ret
                        if math.isinf(ref):
                            ok = d == "INF" and p is None
                        elif isinstance(d, (int, float)) and abs(d - ref) <= 1e-6 and isinstance(p, list) and p \
                                and p[0] == g["s"] and p[-1] == g["t"]:
                            try:
                                cost = sum(edges[(p[k], p[k + 1])] for k in range(len(p) - 1)) if all(
                                    (p[k], p[k + 1]) in edges for k in range(len(p) - 1)) else None
                            except (TypeError, KeyError):
                                cost = None
                            ok = cost is not None and abs(cost - ref) <= 1e-6
                    sh = ok
            correct.append(ok)
            shortest.append(sh)
        n_ok = sum(correct)
        return {"pass": n_ok == len(self.graphs), "frac_correct": n_ok / len(self.graphs),
                "frac_shortest": sum(shortest) / len(self.graphs)}


def sanitize(code: str) -> str:
    """Keep only imports, function/class defs and assignments that do not call module-defined functions or
    print/input. Module-level demo code (example graphs, prints, test calls) is dropped so the oracle scores
    the requested function, not the demo. Falls back to the raw code if it does not parse."""
    import ast
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return code
    defined = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    banned = defined | {"print", "input", "exit", "quit"}
    keep = []
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            keep.append(n)
        elif isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None:
            calls = [c for c in ast.walk(n.value) if isinstance(c, ast.Call)]
            if not any(isinstance(c.func, ast.Name) and c.func.id in banned for c in calls):
                keep.append(n)
    return ast.unparse(ast.Module(body=keep, type_ignores=[]))


def _limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
    os.setsid()


def run_one(args: tuple) -> dict:
    """Worker: (workdir, harness, inst_path, task, func, code, uid). Returns raw records + status."""
    workdir, harness, inst_path, task, func, code, uid = args
    with tempfile.TemporaryDirectory(dir=workdir) as td:
        cp = Path(td) / "candidate.py"
        cp.write_text(sanitize(code))
        op = Path(td) / "out.jsonl"
        status = "ok"
        try:
            subprocess.run([sys.executable, "-I", str(harness), str(cp), str(inst_path), str(op), func],
                           cwd=td, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           preexec_fn=_limits, timeout=20)
        except subprocess.TimeoutExpired:
            status = "timeout"
        recs = []
        if op.exists():
            for line in op.read_text().splitlines():
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    load_err = next((r["load_error"] for r in recs if "load_error" in r), None)
    return {"uid": uid, "recs": recs, "status": status if load_err is None else f"load_error:{load_err}"}
