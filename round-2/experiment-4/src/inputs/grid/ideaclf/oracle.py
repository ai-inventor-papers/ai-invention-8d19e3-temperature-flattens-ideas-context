"""Oracle harness: fixed random instances + sandboxed subprocess execution."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import networkx as nx
import numpy as np

RUNNER = Path(__file__).with_name("oracle_runner.py")
N_INST = 50


def _rand_graph(rng: np.random.Generator, weighted: bool, force_reach: bool) -> dict:
    for _ in range(100):
        n = int(rng.integers(5, 31))
        p = float(rng.uniform(0.1, 0.4))
        edges = []
        for u in range(n):
            for v in range(u + 1, n):
                if rng.random() < p:
                    w = int(rng.integers(1, 21)) if weighted else 1
                    edges.append((u, v, w))
        s, t = (int(x) for x in rng.choice(n, size=2, replace=False))
        G = nx.Graph()
        G.add_nodes_from(range(n))
        G.add_weighted_edges_from(edges)
        reach = nx.has_path(G, s, t)
        if force_reach and not reach:
            continue
        if weighted:
            exp = nx.dijkstra_path_length(G, s, t) if reach else None
        else:
            exp = nx.shortest_path_length(G, s, t) if reach else None
        return {"n": n, "edges": edges, "s": s, "t": t, "reachable": reach, "expected": exp}
    raise RuntimeError("could not build graph")


def _grid_bfs(grid: list, s: tuple, t: tuple, diag: bool) -> int | None:
    from collections import deque
    R, C = len(grid), len(grid[0])
    q = deque([(s, 0)])
    seen = {s}
    while q:
        (r, c), d = q.popleft()
        if (r, c) == t:
            return d
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if (dr, dc) == (0, 0) or (not diag and dr and dc):
                    continue
                rr, cc = r + dr, c + dc
                if 0 <= rr < R and 0 <= cc < C and grid[rr][cc] == 0 and (rr, cc) not in seen:
                    seen.add((rr, cc))
                    q.append(((rr, cc), d + 1))
    return None


@lru_cache(maxsize=4)
def instances(task: str) -> dict:
    """50 graph instances (instance 0 always reachable = smoke) + 50 grid instances (T1)."""
    weighted = task == "T3"
    if task == "T2":
        lists = []
        for i in range(N_INST):
            rng = np.random.default_rng(1000 + i)
            if i == 0:
                lists.append([5, 3, 9, 1, 1, -2, 7, 0])
                continue
            n = int(rng.integers(0, 201))
            if i % 10 == 7:
                lists.append([round(float(x), 3) for x in rng.uniform(-100, 100, size=n)])
            elif i % 5 == 3:
                lists.append([int(x) for x in rng.integers(0, 1000, size=n)])
            else:
                lists.append([int(x) for x in rng.integers(-500, 500, size=n)])
        return {"instances": lists}
    graphs = []
    for i in range(N_INST):
        rng = np.random.default_rng(1000 + i)
        graphs.append(_rand_graph(rng, weighted, force_reach=(i == 0 or i % 5 != 4)))
    grids = []
    if task == "T1":
        for i in range(N_INST):
            rng = np.random.default_rng(5000 + i)
            R, C = int(rng.integers(5, 16)), int(rng.integers(5, 16))
            g = (rng.random((R, C)) < float(rng.uniform(0.15, 0.3))).astype(int).tolist()
            g[0][0] = 0
            g[R - 1][C - 1] = 0
            s, t = (0, 0), (R - 1, C - 1)
            e4 = _grid_bfs(g, s, t, False)
            e8 = _grid_bfs(g, s, t, True)
            if i == 0 and e4 is None:
                g = [[0] * C for _ in range(R)]
                e4, e8 = _grid_bfs(g, s, t, False), _grid_bfs(g, s, t, True)
            grids.append({"grid": g, "s": s, "t": t, "reachable": e4 is not None, "expected": e4,
                          "reachable8": e8 is not None, "expected8": e8})
    return {"instances": graphs, "grid_instances": grids}


def _clean_env() -> dict:
    env = {k: v for k, v in os.environ.items()
           if not any(s in k.upper() for s in ("KEY", "TOKEN", "SECRET", "PASSWORD", "OPENROUTER", "OPENAI"))}
    env["PYTHONHASHSEED"] = "0"
    return env


def run_oracle(code: str, task: str, workdir: Path, timeout: float = 40.0) -> dict:
    """Execute `code` against the task oracle in a sandboxed subprocess."""
    if not code.strip():
        return {"exec_status": "no_code", "pass_rate": 0.0, "adapter": None}
    workdir.mkdir(parents=True, exist_ok=True)
    job = {"task": task, "code": code, **instances(task), "mem_bytes": 2 * 1024 ** 3, "cpu_sec": 35}
    with tempfile.TemporaryDirectory(dir=workdir) as td:
        jp = Path(td) / "job.json"
        jp.write_text(json.dumps(job))
        try:
            pr = subprocess.run([sys.executable, "-I", str(RUNNER), str(jp)], cwd=td, env=_clean_env(),
                                capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return {"exec_status": "timeout", "pass_rate": 0.0, "adapter": None}
    lines = [ln for ln in pr.stdout.strip().splitlines() if ln.startswith("{")]
    if not lines:
        return {"exec_status": "timeout" if pr.returncode in (-9, -24, 137) else "import_fail", "pass_rate": 0.0,
                "adapter": None, "error": (pr.stderr or "")[-200:]}
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return {"exec_status": "import_fail", "pass_rate": 0.0, "adapter": None}
