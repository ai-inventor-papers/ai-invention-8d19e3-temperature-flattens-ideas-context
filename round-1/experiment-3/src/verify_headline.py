#!/usr/bin/env python3
"""Independent re-derivation of headline numbers (TODO 5).

Reads RAW generations (gens/*.jsonl) and the scored files only as a cross-check, and recomputes through a
different code path than src/analysis.py:
  1. idea labels: re-classified from raw text with a small, independent keyword/regex classifier (coarse classes);
     agreement with the AST classifier is reported, and pooled entropies recomputed with pandas.
  2. pass rates: recomputed with pandas from the scored files AND re-executed for a random subset of programs with a
     self-contained checker (its own subprocess runner + its own BFS/Dijkstra references), agreement reported.
  3. placebo: the bootstrap 'CI excludes 0' entropy test is re-run on label-permuted pairs (setting vs its own
     shuffled copy and baseline vs crn re-run) and must FAIL (CI includes 0) there.
Writes results/verify_headline.json.
"""
from __future__ import annotations

import heapq
import json
import math
import random
import re
import subprocess
import sys
import tempfile
from collections import Counter, deque
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent


def jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def coarse_label(text: str) -> str:
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    code = m.group(1) if m else ""
    if not code.strip():
        return "no_code"
    code = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', "", code)
    code = re.sub(r"#.*", "", code)
    if re.search(r"heappop|heapq|PriorityQueue", code):
        return "heap_based"           # dijkstra / astar / greedy / bidirectional-dijkstra
    if re.search(r"popleft\(|pop\(0\)", code):
        return "fifo_based"           # bfs / spfa / bidirectional-bfs
    if re.search(r"\.pop\(\)", code) or re.search(r"def (\w+)\(.*\):[\s\S]*\b\1\(", code):
        return "stack_or_recursive"   # dfs / iddfs
    return "other"


AST2COARSE = {"dijkstra": "heap_based", "astar": "heap_based", "greedy_best_first": "heap_based",
              "bfs": "fifo_based", "spfa": "fifo_based", "dfs": "stack_or_recursive", "iddfs": "stack_or_recursive"}


def ent(labels) -> float:
    c = Counter(l for l in labels if l not in ("no_code", "syntax_error"))
    n = sum(c.values())
    return -sum(v / n * math.log2(v / n) for v in c.values()) if n else 0.0


# ---- independent oracle (own graphs-from-file are reused; checker and references are re-implemented) ----
RUNNER = r'''
import sys, json, copy, os
src, inst, func = sys.argv[1:4]
sys.stdout = open(os.devnull, "w")
import ast
tree = ast.parse(open(src).read())
keep = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef, ast.Assign))]
ns = {"__name__": "x"}
try:
    exec(compile(ast.Module(body=keep, type_ignores=[]), "c", "exec"), ns)
except BaseException:
    pass
out = []
for g in json.load(open(inst)):
    G = {int(k): ([tuple(e) for e in v] if g["weighted"] else list(v)) for k, v in g["graph"].items()}
    try:
        r = ns[func](copy.deepcopy(G), g["s"], g["t"])
        if isinstance(r, tuple): r = list(r)
        if isinstance(r, list) and len(r) == 2 and isinstance(r[0], float) and r[0] == float("inf"): r[0] = "INF"
        out.append(json.dumps(r, default=str))
    except BaseException as e:
        out.append(json.dumps({"err": type(e).__name__}))
sys.stderr.write("\n".join(out))
'''


def ref_sp(g):
    adj = {int(k): v for k, v in g["graph"].items()}
    s, t = g["s"], g["t"]
    if not g["weighted"]:
        seen, q = {s}, deque([s])
        while q:
            u = q.popleft()
            if u == t:
                return True
            for v in adj[u]:
                if v not in seen:
                    seen.add(v); q.append(v)
        return None
    d = {s: 0.0}; pq = [(0.0, s)]
    while pq:
        du, u = heapq.heappop(pq)
        if du > d.get(u, math.inf):
            continue
        for v, w in adj[u]:
            if du + w < d.get(v, math.inf):
                d[v] = du + w; heapq.heappush(pq, (du + w, v))
    return d.get(t, math.inf)


def indep_pass(code: str, task: str, insts: list) -> bool:
    with tempfile.TemporaryDirectory(dir=ROOT / "oracle_tmp") as td:
        Path(td, "c.py").write_text(code)
        Path(td, "r.py").write_text(RUNNER)
        ip = ROOT / "oracle_tmp" / f"instances_{task}.json"
        try:
            p = subprocess.run([sys.executable, "-I", "r.py", "c.py", str(ip), "find_path" if task == "T1" else "shortest_path"],
                               cwd=td, capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL)
            lines = p.stderr.strip().splitlines()
        except subprocess.TimeoutExpired:
            return False
    if len(lines) != len(insts):
        return False
    for g, line in zip(insts, lines):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            return False
        adj = {int(k): v for k, v in g["graph"].items()}
        ref = ref_sp(g)
        if task == "T1":
            edges = {(u, v) for u, vs in adj.items() for v in vs}
            if ref is None:
                if r is not None:
                    return False
            elif not (isinstance(r, list) and r and r[0] == g["s"] and r[-1] == g["t"]
                      and all((r[i], r[i + 1]) in edges for i in range(len(r) - 1))):
                return False
        else:
            ew = {(u, v): w for u, vs in adj.items() for v, w in vs}
            if not (isinstance(r, list) and len(r) == 2):
                return False
            d, path = r
            if math.isinf(ref):
                if not (d == "INF" and path is None):
                    return False
            else:
                if not isinstance(d, (int, float)) or abs(d - ref) > 1e-6 or not isinstance(path, list) or not path:
                    return False
                if path[0] != g["s"] or path[-1] != g["t"]:
                    return False
                if not all((path[i], path[i + 1]) in ew for i in range(len(path) - 1)):
                    return False
                if abs(sum(ew[(path[i], path[i + 1])] for i in range(len(path) - 1)) - ref) > 1e-6:
                    return False
    return True


def boot_ci_diff(a, b, B=1000, rng=None):
    rng = rng or np.random.default_rng(0)
    vals = [ent([a[i] for i in rng.integers(0, len(a), len(a))]) - ent([b[i] for i in rng.integers(0, len(b), len(b))])
            for _ in range(B)]
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return float(lo), float(hi)


def main() -> None:
    sys.path.insert(0, str(ROOT))
    out = {}
    rows = []
    for t in ("T1", "T3"):
        for p in sorted((ROOT / "gens" / t).glob("*.jsonl")):
            if p.stem.startswith("calib") or p.stem.endswith("_list"):
                continue
            g = {r["idx"]: r for r in jl(p)}
            s = {r["idx"]: r for r in jl(ROOT / "scored" / t / p.name)}
            for i, r in g.items():
                if i in s:
                    rows.append({"task": t, "setting": p.stem, "idx": i, "coarse": coarse_label(r["text"]),
                                 "ast": s[i]["label"], "pass": bool(s[i]["pass"]), "text": r["text"]})
    df = pd.DataFrame(rows)
    df = df[~((df.setting == "baseline") & (df.idx >= 150))]
    m = df[df.ast.isin(AST2COARSE)]
    out["coarse_vs_ast_agreement"] = float((m.ast.map(AST2COARSE) == m.coarse).mean())
    # pandas re-derivation of per-setting pooled pass and AST-label entropy
    agg = {}
    for (st, t), g in df.groupby(["setting", "task"]):
        agg.setdefault(st, {})[t] = {"pass": float(g["pass"].mean()), "entropy_ast": ent(g.ast.tolist()),
                                     "entropy_coarse": ent(g.coarse.tolist()), "n": int(len(g))}
    out["per_setting"] = {st: {**v, "pooled_pass": float(np.mean([v[t]["pass"] for t in v])) if len(v) == 2 else None,
                               "pooled_entropy_ast": float(np.mean([v[t]["entropy_ast"] for t in v])) if len(v) == 2 else None}
                          for st, v in agg.items()}
    # independent oracle re-execution on a random subset
    rng = random.Random(0)
    insts = {t: json.loads((ROOT / "oracle_tmp" / f"instances_{t}.json").read_text()) for t in ("T1", "T3")}
    sub = df[df.ast.notna() & ~df.ast.isin(["no_code", "syntax_error"])].sample(n=min(150, len(df)), random_state=0)
    agree = []
    for _, r in sub.iterrows():
        mm = re.search(r"```(?:python|py)?\s*\n(.*?)```", r.text, re.S)
        if not mm:
            continue
        agree.append(indep_pass(mm.group(1), r.task, insts[r.task]) == r["pass"])
    out["independent_oracle_agreement"] = {"n": len(agree), "agreement": float(np.mean(agree)) if agree else None}
    # placebo tests for the bootstrap 'CI excludes 0' entropy test
    pl = {}
    rng2 = np.random.default_rng(1)
    for t in ("T1", "T3"):
        b = df[(df.setting == "baseline") & (df.task == t)].ast.tolist()
        c = df[(df.setting == "crn_rerun") & (df.task == t)].ast.tolist()
        lo, hi = boot_ci_diff(b, c, rng=rng2)
        pl[f"{t}_baseline_vs_crn_rerun"] = {"ci": [lo, hi], "excludes_0": bool(lo > 0 or hi < 0)}
        # permutation placebo: pool baseline with ban3, randomly split into two halves 20x
        ban = df[(df.setting == "prompt_ban3") & (df.task == t)].ast.tolist()
        pool = b + ban
        exc = 0
        for k in range(20):
            perm = rng2.permutation(len(pool))
            a1 = [pool[i] for i in perm[:len(b)]]
            a2 = [pool[i] for i in perm[len(b):]]
            lo, hi = boot_ci_diff(a1, a2, B=300, rng=rng2)
            exc += (lo > 0 or hi < 0)
        lo, hi = boot_ci_diff(ban, b, rng=rng2)
        pl[f"{t}_ban3_vs_baseline_real"] = {"ci": [lo, hi], "excludes_0": bool(lo > 0 or hi < 0)}
        pl[f"{t}_permuted_split_excludes0_rate"] = exc / 20
    out["placebo"] = pl
    (ROOT / "results" / "verify_headline.json").write_text(json.dumps(out, indent=1))
    keys = ["baseline", "crn_rerun", "prompt_ban3", "prompt_new", "temp1.0"]
    for k in keys:
        if k in out["per_setting"]:
            v = out["per_setting"][k]
            print(k, {t: (round(v[t]["pass"], 3), round(v[t]["entropy_ast"], 3)) for t in ("T1", "T3") if t in v})
    print("coarse agreement", out["coarse_vs_ast_agreement"], "oracle agreement", out["independent_oracle_agreement"])
    print(json.dumps(pl, indent=1))


if __name__ == "__main__":
    main()
