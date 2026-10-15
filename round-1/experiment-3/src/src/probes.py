"""Per-layer multinomial idea probes (worker functions for a spawn ProcessPool)."""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import warnings  # noqa: E402

import numpy as np  # noqa: E402
from sklearn.exceptions import ConvergenceWarning  # noqa: E402

from src.acts_io import load_acts  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import balanced_accuracy_score  # noqa: E402
from sklearn.model_selection import StratifiedKFold  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

warnings.filterwarnings("ignore", category=ConvergenceWarning)
C_GRID = (0.01, 0.1, 1.0)


def load_layer(acts_dir: str, layer: int, pos: slice | int = slice(1, 9)) -> np.ndarray:
    xs = []
    for t in ("T1", "T3"):
        a = load_acts(acts_dir, t)
        x = a[:, pos, layer, :].astype(np.float32)
        if x.ndim == 3:
            x = x.mean(1)
        xs.append(x)
    return np.concatenate(xs, 0)


def _fit_predict(Xtr, ytr, Xte, C):
    sc = StandardScaler().fit(Xtr)
    clf = LogisticRegression(C=C, max_iter=300, tol=1e-3)
    clf.fit(sc.transform(Xtr), ytr)
    return clf.predict(sc.transform(Xte))


def cv_bal_acc(X, y, tasks, C, seed=0, n_splits=5):
    strat = np.array([f"{t}_{c}" for t, c in zip(tasks, y)])
    # merge strata with < n_splits members into a per-task stratum
    vals, cnts = np.unique(strat, return_counts=True)
    small = set(vals[cnts < n_splits])
    strat = np.array([s if s not in small else s.split("_")[0] + "_small" for s in strat])
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    pred = np.zeros_like(y)
    for tr, te in skf.split(X, strat):
        if len(np.unique(y[tr])) < 2:
            pred[te] = y[tr][0]
            continue
        pred[te] = _fit_predict(X[tr], y[tr], X[te], C)
    out = {"pooled": float(balanced_accuracy_score(y, pred))}
    for t in np.unique(tasks):
        m = tasks == t
        out[str(t)] = float(balanced_accuracy_score(y[m], pred[m])) if len(np.unique(y[m])) > 1 else float("nan")
    return out


def choose_C(X, y, tasks):
    best, bc = -1, C_GRID[1]
    for C in C_GRID:
        s = cv_bal_acc(X, y, tasks, C, seed=1, n_splits=3)["pooled"]
        if s > best:
            best, bc = s, C
    return bc


def probe_layer(acts_dir: str, layer: int, y: list, tasks: list) -> dict:
    y = np.array(y)
    tasks = np.array(tasks)
    # F4 fallback (pre-registered): gen1..8 probes are at chance (boilerplate opening tokens), so the primary
    # probe feature is mean(gen1..32)
    X = load_layer(acts_dir, layer, pos=9)
    C = choose_C(X, y, tasks)
    real = cv_bal_acc(X, y, tasks, C)
    rng = np.random.default_rng(1000 + layer)
    shuf = []
    for p in range(5):
        ys = y.copy()
        for t in np.unique(tasks):
            m = np.where(tasks == t)[0]
            ys[m] = ys[rng.permutation(m)]
        shuf.append(cv_bal_acc(X, ys, tasks, C, seed=p))
    per_pos = {}
    for k in range(1, 9):
        Xk = load_layer(acts_dir, layer, pos=k)
        per_pos[f"gen{k}"] = cv_bal_acc(Xk, y, tasks, 0.1)["pooled"]
    X8 = load_layer(acts_dir, layer, pos=slice(1, 9))
    per_pos["mean_gen1_8"] = cv_bal_acc(X8, y, tasks, 0.1)["pooled"]
    per_pos["mean_gen1_32"] = real["pooled"]
    return {
        "layer": layer, "C": C, "bal_acc_pooled": real["pooled"], "bal_acc_T1": real.get("T1"),
        "bal_acc_T3": real.get("T3"),
        "shuf_bal_acc_pooled": float(np.mean([s["pooled"] for s in shuf])),
        "shuf_bal_acc_pooled_sd": float(np.std([s["pooled"] for s in shuf])),
        "shuf_bal_acc_T1": float(np.nanmean([s.get("T1", np.nan) for s in shuf])),
        "shuf_bal_acc_T3": float(np.nanmean([s.get("T3", np.nan) for s in shuf])),
        "per_position_bal_acc": per_pos,
    }


def erasure_check(X: np.ndarray, y: np.ndarray, seed: int = 0) -> float:
    """5-fold balanced accuracy of a fresh probe (single task) -> used for LEACE offline check."""
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    vals, cnts = np.unique(y, return_counts=True)
    ok = np.isin(y, vals[cnts >= 5])
    X, y = X[ok], y[ok]
    if len(np.unique(y)) < 2:
        return float("nan")
    pred = np.zeros_like(y)
    for tr, te in skf.split(X, y):
        pred[te] = _fit_predict(X[tr], y[tr], X[te], 0.1)
    return float(balanced_accuracy_score(y, pred))
