"""Shared paths, IO, logging and statistics helpers for every stage of this artifact.

All paths are derived from this file's location; nothing writes outside the workspace.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
INPUTS = ROOT / "inputs"
RESULTS = ROOT / "results"
FIGS = ROOT / "figures"
LOGS = ROOT / "logs"
GENS = ROOT / "gens"
for _d in (RESULTS, FIGS, LOGS, GENS):
    _d.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SRC))

MODEL = "Qwen/Qwen2.5-3B-Instruct"
TEMPS = [0.3, 0.5, 0.7, 1.0, 1.3, 1.6]
TOPKS = [10, -1]
TASKS = ["T1", "T2", "T3"]
NON_IDEAS = {"Other", "Unparseable"}
# P4 menus (classes >= 3% in the P1 baseline n=300); recomputed and asserted in s3_screen.py
MENUS = {"T1": ["BFS", "DFS", "A_star", "Dijkstra"], "T2": ["Bubble", "Quick", "Merge", "Selection"],
         "T3": ["Dijkstra"]}
RARE_CORRECT = {"T1": ["A_star", "Bidirectional", "IDDFS", "Bellman_Ford", "SPFA"],
                "T2": ["Counting", "Radix", "Heap"], "T3": ["A_star", "Bidirectional", "Bellman_Ford", "SPFA"]}
LABELS_PATH = RESULTS / "labels_unified.jsonl"
ORACLE_PATH = RESULTS / "oracle_results.jsonl"


def setup_logging(name: str) -> None:
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
    logger.add(LOGS / f"{name}.log", rotation="30 MB", level="DEBUG")


def detect_cpus() -> int:
    try:
        q = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text())
        p = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text())
        if q > 0:
            return math.ceil(q / p)
    except (FileNotFoundError, ValueError):
        pass
    try:
        parts = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if parts[0] != "max":
            return math.ceil(int(parts[0]) / int(parts[1]))
    except (FileNotFoundError, ValueError):
        pass
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def set_ram_limit(gb: float) -> None:
    import resource
    b = int(gb * 1024 ** 3)
    resource.setrlimit(resource.RLIMIT_AS, (b, b))


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def write_jsonl(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, default=_json_default) + "\n")
    tmp.replace(p)


def _json_default(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        f = float(o)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, tuple)):
        return list(o)
    if isinstance(o, Path):
        return str(o.relative_to(ROOT)) if o.is_absolute() and ROOT in o.parents else str(o)
    raise TypeError(f"not serializable: {type(o)}")


def _clean(o):
    """Replace NaN/inf floats by None recursively so the JSON is strict."""
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.floating):
        return _clean(float(o))
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def save_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(_clean(obj), indent=1, default=_json_default))
    tmp.replace(p)


def load_json(p: Path):
    return json.loads(p.read_text())


def canonical_sha(obj) -> str:
    return hashlib.sha256(json.dumps(_clean(obj), sort_keys=True, default=_json_default).encode()).hexdigest()


def rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return Path(p).name


# ----------------------------------------------------------------------------- statistics
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return p, max(0.0, c - h), min(1.0, c + h)


def entropy_bits(counts) -> float:
    c = np.asarray([v for v in counts if v > 0], dtype=float)
    if c.sum() == 0:
        return 0.0
    p = c / c.sum()
    return float(-(p * np.log2(p)).sum())


def hill(counts) -> dict:
    c = np.asarray([v for v in counts if v > 0], dtype=float)
    if c.sum() == 0:
        return dict(D0=0, D1=float("nan"), D2=float("nan"))
    p = c / c.sum()
    return dict(D0=int(len(c)), D1=float(np.exp(-(p * np.log(p)).sum())), D2=float(1.0 / (p * p).sum()))


def rarefied_richness(counts, k: int) -> float:
    """Expected number of distinct classes among k draws without replacement (Hurlbert 1971)."""
    c = [int(v) for v in counts if v > 0]
    n = sum(c)
    if n == 0:
        return float("nan")
    if k >= n:
        return float(len(c))
    lt = math.lgamma
    lc_nk = lt(n + 1) - lt(k + 1) - lt(n - k + 1)
    s = 0.0
    for ni in c:
        if n - ni >= k:
            s += 1 - math.exp(lt(n - ni + 1) - lt(k + 1) - lt(n - ni - k + 1) - lc_nk)
        else:
            s += 1.0
    return s


def chao1(counts) -> float:
    c = [int(v) for v in counts if v > 0]
    f1 = sum(1 for v in c if v == 1)
    f2 = sum(1 for v in c if v == 2)
    return len(c) + f1 * (f1 - 1) / (2 * (f2 + 1))


def jsd_bits(p: dict, q: dict) -> float:
    keys = sorted(set(p) | set(q))
    a = np.array([p.get(k, 0.0) for k in keys], float)
    b = np.array([q.get(k, 0.0) for k in keys], float)
    if a.sum() == 0 or b.sum() == 0:
        return float("nan")
    a, b = a / a.sum(), b / b.sum()
    m = (a + b) / 2

    def kl(x, y):
        mask = x > 0
        return float((x[mask] * np.log2(x[mask] / y[mask])).sum())
    return 0.5 * kl(a, m) + 0.5 * kl(b, m)


def shares(labels: list[str]) -> dict:
    c = Counter(labels)
    n = sum(c.values())
    return {k: v / n for k, v in c.items()} if n else {}


def holm(pvals: list[float]) -> list[float]:
    m = len(pvals)
    order = np.argsort(pvals)
    adj = np.empty(m)
    run = 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (m - r) * pvals[i]))
        adj[i] = run
    return adj.tolist()


def bootstrap_ci(values_fn, n_items: int, n_boot: int = 2000, seed: int = 0, alpha: float = 0.05):
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(n_boot):
        idx = rng.integers(0, n_items, n_items)
        stats.append(values_fn(idx))
    stats = np.asarray(stats, float)
    stats = stats[~np.isnan(stats)]
    if len(stats) == 0:
        return float("nan"), float("nan")
    return float(np.quantile(stats, alpha / 2)), float(np.quantile(stats, 1 - alpha / 2))


def entropy_ci(labels: list[str], n_boot: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    arr = np.asarray(labels)
    h = entropy_bits(Counter(labels).values())
    if len(arr) == 0:
        return h, float("nan"), float("nan")
    lo, hi = bootstrap_ci(lambda idx: entropy_bits(Counter(arr[idx].tolist()).values()), len(arr), n_boot, seed)
    return h, lo, hi


# ----------------------------------------------------------------------------- code normalisation
_PY_KW = set("""False None True and as assert async await break class continue def del elif else except finally for
from global if import in is lambda nonlocal not or pass raise return try while with yield print range len int float str
list dict set tuple min max sorted sum abs enumerate zip map filter any all isinstance self append pop popleft heappush
heappop heapq deque collections inf math float""".split())
_TOK = re.compile(r"[A-Za-z_]\w*|\d+(?:\.\d+)?|==|!=|<=|>=|\*\*|//|\+=|-=|[^\s\w]")


def normalise_code_tokens(code: str, max_tokens: int = 400) -> list[str]:
    """Strip comments/docstrings (classify.strip_code), rename identifiers to v0, v1... in order of first
    appearance (keywords/builtins kept), tokenize, cut at max_tokens so truncated and full programs compare."""
    from classify import strip_code
    if not code:
        return []
    src, _tree, _ok = strip_code(code)
    names: dict[str, str] = {}
    out = []
    for t in _TOK.findall(src):
        if (t[0].isalpha() or t[0] == "_") and t not in _PY_KW:
            if t not in names:
                names[t] = f"v{len(names)}"
            t = names[t]
        out.append(t)
        if len(out) >= max_tokens:
            break
    return out
