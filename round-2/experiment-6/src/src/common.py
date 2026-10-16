"""Shared paths, I/O, resource limits and statistics for the selector / gemma-ban experiment.

Every statistic used by the verdicts lives here (entropy with Miller-Madow correction, Wilson CIs, KL to uniform,
base-2 JSD, hierarchical draw->sample bootstrap) so the stages and verify.py share one implementation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import resource
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
DATA = ROOT / "data"
GENS = DATA / "gens"          # gens/<model>/<task>/<setting>.jsonl
SCORED = DATA / "scored"      # scored/<model>/<task>/<setting>.jsonl
ACTS = DATA / "acts"
RESULTS = ROOT / "results"
FIGS = ROOT / "figs"
LOGS = ROOT / "logs"
for _d in (GENS, SCORED, ACTS, RESULTS, FIGS, LOGS):
    _d.mkdir(parents=True, exist_ok=True)

# Iteration-1 inputs (READ-ONLY), resolved relative to this folder; override with the environment variables.
#   influence arm = art_aSN7z8WuA7Ir (iteration-1 gen_art_experiment_3); ban arm = iteration-1 gen_art_experiment_2
_ITER1 = ROOT.parents[2] / "round-1" / "."
IA = Path(os.environ.get("AII_INFLUENCE_ARM_DIR", _ITER1 / "gen_art_experiment_3"))
BA = Path(os.environ.get("AII_BAN_ARM_DIR", _ITER1 / "gen_art_experiment_2"))

QWEN = "Qwen/Qwen2.5-3B-Instruct"
GEMMA = "google/gemma-2-2b-it"
MODEL_TAG = {QWEN: "qwen", GEMMA: "gemma"}
P4_MENU = {"T1": ["BFS", "DFS", "A_star", "Dijkstra"], "T2": ["Bubble", "Quick", "Merge", "Selection"]}
MODE = {"T1": "BFS", "T2": "Bubble"}


# ----------------------------------------------------------------------------------------------- resources
def container_ram_gb() -> float:
    for p in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            v = Path(p).read_text().strip()
            if v != "max" and int(v) < 1_000_000_000_000:
                return int(v) / 1e9
        except (FileNotFoundError, ValueError):
            pass
    return 28.0


def set_ram_limit(gb: float) -> None:
    """Hard address-space cap so a runaway raises MemoryError instead of OOM-killing the container."""
    b = int(gb * 1024 ** 3)
    resource.setrlimit(resource.RLIMIT_AS, (b, b))


# ----------------------------------------------------------------------------------------------- I/O
def read_jsonl(p: Path) -> list[dict]:
    p = Path(p)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a partially written trailing line after an interruption
    return out


def append_jsonl(p: Path, rows: list[dict]) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def write_json(p: Path, obj) -> None:
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, indent=1, default=_json_default))


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, tuple)):
        return list(o)
    raise TypeError(type(o))


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def freeze(p: Path, obj: dict) -> str:
    """Write a frozen pre-registration file and its .sha256 sidecar; refuse to overwrite a different freeze."""
    p = Path(p)
    txt = json.dumps(obj, indent=1, default=_json_default)
    h = hashlib.sha256(txt.encode()).hexdigest()
    side = p.with_suffix(p.suffix + ".sha256")
    if p.exists() and side.exists():
        old = side.read_text().split()[0]
        if old != h:
            raise RuntimeError(f"{p.name} already frozen with a different hash ({old[:12]} vs {h[:12]})")
        return h
    p.write_text(txt)
    side.write_text(f"{h}  {p.name}\n")
    return h


def require_frozen(p: Path) -> str:
    p = Path(p)
    side = p.with_suffix(p.suffix + ".sha256")
    if not p.exists() or not side.exists():
        raise SystemExit(f"frozen file missing: {p.name} -> refusing to run")
    h = sha256_file(p)
    if h != side.read_text().split()[0]:
        raise SystemExit(f"frozen file {p.name} hash mismatch -> refusing to run")
    return h


# ----------------------------------------------------------------------------------------------- statistics
def counts(labels: list[str]) -> Counter:
    return Counter(labels)


def entropy_bits(labels) -> float:
    c = np.array(list(Counter(labels).values()), float)
    if c.sum() == 0:
        return float("nan")
    p = c / c.sum()
    return float(-(p * np.log2(p)).sum())


def entropy_mm(labels) -> float:
    """Miller-Madow bias-corrected plug-in entropy (bits): H + (K_obs-1)/(2 n ln 2)."""
    n = len(labels)
    if n == 0:
        return float("nan")
    k = len(set(labels))
    return entropy_bits(labels) + (k - 1) / (2 * n * math.log(2))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def dist(labels: list[str], support: list[str], pseudo: float = 0.0) -> np.ndarray:
    c = Counter(labels)
    v = np.array([c.get(s, 0) + pseudo for s in support], float)
    return v / v.sum() if v.sum() > 0 else np.full(len(support), 1 / len(support))


def kl_uniform(labels: list[str], support: list[str]) -> float:
    """KL(p || uniform on U) in bits; labels outside U are mapped to 'Other' if present else dropped."""
    lab = [x if x in support else ("Other" if "Other" in support else None) for x in labels]
    lab = [x for x in lab if x is not None]
    p = dist(lab, support)
    nz = p > 0
    return float((p[nz] * np.log2(p[nz] * len(support))).sum())


def jsd2(p: np.ndarray, q: np.ndarray) -> float:
    p = np.asarray(p, float) / np.sum(p)
    q = np.asarray(q, float) / np.sum(q)
    m = 0.5 * (p + q)

    def _kl(a, b):
        nz = a > 0
        return float((a[nz] * np.log2(a[nz] / b[nz])).sum())
    return 0.5 * _kl(p, m) + 0.5 * _kl(q, m)


def hier_boot_diff(target: list[str], draws: list[list[str]], stat, B: int = 10000, seed: int = 20261016,
                   target_draws: list[list[str]] | None = None) -> dict:
    """Hierarchical bootstrap of stat(target) - mean_d stat(draw_d).

    Random arm: resample draws with replacement, then samples within each drawn draw. Targeted arm: resample its
    samples (or, when target_draws is given, its draws then samples). Returns point estimate, 95% percentile CI,
    P(diff > 0)."""
    rng = np.random.default_rng(seed)
    point_r = float(np.mean([stat(d) for d in draws]))
    t_arms = target_draws if target_draws is not None else [target]
    point_t = float(np.mean([stat(d) for d in t_arms]))
    t_arr = [np.array(d, dtype=object) for d in t_arms]
    d_arr = [np.array(d, dtype=object) for d in draws]
    out = np.empty(B)
    for b in range(B):
        ti = rng.integers(0, len(t_arr), len(t_arr)) if len(t_arr) > 1 else [0]
        st = np.mean([stat(list(t_arr[i][rng.integers(0, len(t_arr[i]), len(t_arr[i]))])) for i in ti])
        di = rng.integers(0, len(d_arr), len(d_arr))
        sr = np.mean([stat(list(d_arr[i][rng.integers(0, len(d_arr[i]), len(d_arr[i]))])) for i in di])
        out[b] = st - sr
    lo, hi = np.percentile(out, [2.5, 97.5])
    return dict(diff=point_t - point_r, target=point_t, random_draw_mean=point_r,
                random_per_draw=[float(stat(d)) for d in draws], ci=[float(lo), float(hi)],
                p_gt0=float((out > 0).mean()), B=B,
                verdict=("beats" if lo > 0 else "below" if hi < 0 else "undetermined"))


def boot_ci(x: list, stat, B: int = 5000, seed: int = 0) -> list[float]:
    rng = np.random.default_rng(seed)
    a = np.array(x, dtype=object)
    vals = [stat(list(a[rng.integers(0, len(a), len(a))])) for _ in range(B)]
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


# ----------------------------------------------------------------------------------------------- vectorized bootstrap
def encode(groups: list[list], exclude: set | None = None) -> tuple[list[np.ndarray], list]:
    """Map labels to ints (shared vocabulary); excluded (non-idea) labels -> -1."""
    exclude = exclude or set()
    vocab = sorted({x for g in groups for x in g if x not in exclude}, key=str)
    ix = {v: i for i, v in enumerate(vocab)}
    return [np.array([ix.get(x, -1) for x in g], int) for g in groups], vocab


def _stat_rows(M: np.ndarray, K: int, stat: str) -> np.ndarray:
    """M: [R, n] int labels (-1 = excluded) or 0/1 values for 'mean'. Returns stat per row."""
    if stat == "mean":
        return M.mean(1)
    oh = np.zeros((M.shape[0], K), float)
    for k in range(K):
        oh[:, k] = (M == k).sum(1)
    n = oh.sum(1, keepdims=True)
    p = np.divide(oh, n, out=np.zeros_like(oh), where=n > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        h = -np.nansum(np.where(p > 0, p * np.log2(p), 0.0), 1)
    if stat == "H_mm":
        kobs = (oh > 0).sum(1)
        h = h + (kobs - 1) / (2 * np.maximum(n[:, 0], 1) * math.log(2))
    return h


def stat_point(x: np.ndarray, K: int, stat: str) -> float:
    return float(_stat_rows(x[None, :], K, stat)[0])


def _boot_matrix(x: np.ndarray, K: int, stat: str, B: int, m: int, rng) -> np.ndarray:
    """[B, m] independent within-sample bootstrap stats of one cell."""
    n = len(x)
    out = np.empty((B, m))
    for j in range(m):
        idx = rng.integers(0, n, (B, n))
        out[:, j] = _stat_rows(x[idx], K, stat)
    return out


def hier_boot(target: list[np.ndarray], draws: list[np.ndarray], K: int, stat: str, B: int = 10000,
              seed: int = 20261016) -> dict:
    """Hierarchical bootstrap of mean_t stat(target_t) - mean_d stat(draw_d).

    Each arm with >1 draw: resample draws with replacement, then samples within each chosen draw
    (independent resamples per slot). Single-draw arms: resample samples only."""
    rng = np.random.default_rng(seed)

    def arm(cells):
        m = len(cells)
        mats = [_boot_matrix(c, K, stat, B, m, rng) for c in cells]
        if m == 1:
            return mats[0][:, 0]
        pick = rng.integers(0, m, (B, m))
        vals = np.stack([np.stack(mats, 0)[pick[:, j], np.arange(B), j] for j in range(m)], 1)
        return vals.mean(1)
    bt, br = arm(target), arm(draws)
    d = bt - br
    pt = float(np.mean([stat_point(c, K, stat) for c in target]))
    pr_each = [stat_point(c, K, stat) for c in draws]
    pr = float(np.mean(pr_each))
    lo, hi = np.percentile(d, [2.5, 97.5])
    return dict(target=pt, random_draw_mean=pr, random_per_draw=pr_each, diff=pt - pr, ci=[float(lo), float(hi)],
                p_gt0=float((d > 0).mean()), B=B, n_target=[len(c) for c in target], n_draws=[len(c) for c in draws],
                verdict=("beats" if lo > 0 else "below" if hi < 0 else "undetermined"))
