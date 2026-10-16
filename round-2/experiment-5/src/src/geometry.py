#!/usr/bin/env python3
"""Geometry from UNBANNED runs only: layer choice by probe CV, centroids, S matrices, stability,
behavioural (co-mention) and lexical (name-embedding) similarity controls.

Outputs: results/geometry/geometry.json (+ geometry_{task}.npz with centroids and S for all layers/variants).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from joblib import Parallel, delayed
from loguru import logger
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import parse_list_names  # noqa: E402
from protocol import ACTS, DATA, DISPLAY, GEN, LAYERS, LOGS, MODEL, RESULTS, TASK_KIND, TASKS, bannable, taxonomy  # noqa: E402

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
logger.add(LOGS / "geometry.log", rotation="30 MB", level="DEBUG")
GEO = RESULTS / "geometry"
MIN_NAT = 8


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def load_cond(task: str, cond: str) -> tuple[list[dict], dict]:
    labs = load_jsonl(DATA / "labels" / task / f"{cond}.jsonl")
    a = np.load(ACTS / task / f"{cond}.npz")
    acts = {k: a[k] for k in a.files}
    assert list(acts["ids"]) == [r["id"] for r in labs], f"id mismatch {task}/{cond}"
    return labs, acts


# ----------------------------------------------------------------------------- probes
def _probe_one(X: np.ndarray, y: np.ndarray, seed: int, shuffle: bool) -> float:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import balanced_accuracy_score
    from sklearn.model_selection import StratifiedKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    rng = np.random.default_rng(seed)
    yy = rng.permutation(y) if shuffle else y
    skf = StratifiedKFold(5, shuffle=True, random_state=seed)
    pred = np.empty_like(yy)
    for tr, te in skf.split(X, yy):
        clf = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
        clf.fit(X[tr], yy[tr])
        pred[te] = clf.predict(X[te])
    return float(balanced_accuracy_score(yy, pred))


def probe_sweep(task: str, labs: list[dict], acts: dict, pooling: str = "window") -> dict:
    y_all = np.array([r["label"] for r in labs])
    cnt = Counter(y_all)
    keep_cls = sorted(c for c, n in cnt.items() if n >= MIN_NAT and c != "Unparseable")
    if len(keep_cls) < 2:
        return dict(classes=keep_cls, skipped=True)
    m = np.isin(y_all, keep_cls)
    X_all = acts[pooling].astype(np.float32)
    if pooling == "precommit":
        m &= ~np.isnan(X_all[:, 0, 0])
    y = y_all[m]
    jobs = []
    for li in range(len(LAYERS)):
        X = X_all[m, li]
        jobs.append((li, False, 0, X))
        for s in range(5):
            jobs.append((li, True, s + 1, X))
    res = Parallel(n_jobs=10)(delayed(_probe_one)(X, y, sd, sh) for (_, sh, sd, X) in jobs)
    out = dict(classes=keep_cls, n=int(m.sum()), chance=1 / len(keep_cls), real={}, shuffled_mean={},
               shuffled_p95={})
    for (li, sh, sd, _), r in zip(jobs, res):
        L = str(LAYERS[li])
        if not sh:
            out["real"][L] = r
        else:
            out.setdefault("_sh", {}).setdefault(L, []).append(r)
    for L, v in out.pop("_sh").items():
        out["shuffled_mean"][L] = float(np.mean(v))
        out["shuffled_p95"][L] = float(np.percentile(v, 95))
    return out


# ----------------------------------------------------------------------------- centroids / S
def cos_matrix(C: np.ndarray) -> np.ndarray:
    """C: [K, d] with NaN rows for missing classes -> cosine matrix with NaN rows/cols."""
    n = np.linalg.norm(C, axis=1, keepdims=True)
    U = C / np.where(n == 0, 1, n)
    S = U @ U.T
    S[np.isnan(C[:, 0])] = np.nan
    S[:, np.isnan(C[:, 0])] = np.nan
    return S


def centroids(task: str, X: np.ndarray, labels: np.ndarray, forced: dict[str, np.ndarray], mu: np.ndarray,
              classes: list[str], forced_only: bool = False) -> tuple[np.ndarray, list[str]]:
    """X: [N, d] baseline pooled at one layer (raw), forced: class -> [n, d] raw. Returns [K, d], sources."""
    K, d = len(classes), X.shape[1]
    C = np.full((K, d), np.nan, np.float64)
    src = ["none"] * K
    Xc = X - mu
    for k, c in enumerate(classes):
        m = labels == c
        if not forced_only and m.sum() >= MIN_NAT:
            C[k] = Xc[m].mean(0)
            src[k] = "natural"
        elif c in forced and len(forced[c]) > 0:
            C[k] = (forced[c] - mu).mean(0)
            src[k] = "forced"
    return C, src


def offdiag(S: np.ndarray, idx: list[int]) -> np.ndarray:
    sub = S[np.ix_(idx, idx)]
    iu = np.triu_indices(len(idx), 1)
    return sub[iu]


def split_half(X: np.ndarray, labels: np.ndarray, classes: list[str], n_splits: int = 200, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    cnt = Counter(labels)
    ok = [c for c in classes if cnt.get(c, 0) >= 8]
    if len(ok) < 3:
        return dict(n_classes=len(ok), median=None)
    mu = X.mean(0)
    rhos = []
    for _ in range(n_splits):
        A, B = [], []
        for c in ok:
            ids = rng.permutation(np.where(labels == c)[0])
            h = len(ids) // 2
            A.append((X[ids[:h]] - mu).mean(0))
            B.append((X[ids[h:2 * h]] - mu).mean(0))
        SA, SB = cos_matrix(np.array(A)), cos_matrix(np.array(B))
        iu = np.triu_indices(len(ok), 1)
        rhos.append(spearmanr(SA[iu], SB[iu]).statistic)
    return dict(n_classes=len(ok), classes=ok, median=float(np.nanmedian(rhos)),
                p5=float(np.nanpercentile(rhos, 5)), p95=float(np.nanpercentile(rhos, 95)))


def scale_offdiag(M: np.ndarray) -> np.ndarray:
    K = M.shape[0]
    mask = ~np.eye(K, dtype=bool)
    v = M[mask]
    mu = v.mean()
    den = np.max(np.abs(v - mu)) or 1.0
    out = (M - mu) / den
    np.fill_diagonal(out, 1.0)
    return out


def behavioural_S(lists: list[list[str]], classes: list[str]) -> dict[str, np.ndarray]:
    K = len(classes)
    idx = {c: i for i, c in enumerate(classes)}
    acc = np.zeros((K, K))
    n_both = np.zeros((K, K))
    occ = np.zeros(K)
    for lst in lists:
        pos = {}
        for p, c in enumerate(lst):
            if c in idx and c not in pos:
                pos[c] = p
        for c in pos:
            occ[idx[c]] += 1
        for a in pos:
            for b in pos:
                if a != b:
                    acc[idx[a], idx[b]] += 1.0 / abs(pos[a] - pos[b])
                    n_both[idx[a], idx[b]] += 1
    rank = np.where(n_both > 0, acc / np.maximum(n_both, 1), 0.0)
    N = max(len(lists), 1)
    pa = (occ + 0.5) / (N + 1)
    pab = (n_both + 0.5) / (N + 1)
    pmi = np.log(pab / np.outer(pa, pa))
    return dict(rank=scale_offdiag(rank), pmi=scale_offdiag(pmi))


def lexical_S(classes: list[str]) -> np.ndarray:
    """Cosine of mean input-embedding vectors of DISPLAY names, centered by the mean over classes."""
    from huggingface_hub import snapshot_download
    from safetensors import safe_open
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL)
    path = Path(snapshot_download(MODEL, allow_patterns=["*.safetensors", "*.json"]))
    W = None
    for f in sorted(path.glob("*.safetensors")):
        with safe_open(str(f), framework="pt") as fh:
            if "model.embed_tokens.weight" in fh.keys():
                W = fh.get_tensor("model.embed_tokens.weight").float().numpy()
                break
    assert W is not None
    names = [DISPLAY.get(c, c.replace("_", " ")) for c in classes]
    V = np.array([W[tok(n, add_special_tokens=False)["input_ids"]].mean(0) for n in names])
    V = V - V.mean(0)
    return cos_matrix(V)


@logger.catch(reraise=True)
def main() -> None:
    GEO.mkdir(parents=True, exist_ok=True)
    summary: dict = dict(layers=LAYERS, tasks={})
    probe_all = {}
    data = {}
    for t in TASKS:
        labs, acts = load_cond(t, "baseline")
        data[t] = (labs, acts)
        logger.info(f"{t}: probe sweep")
        probe_all[t] = probe_sweep(t, labs, acts, "window")
        logger.info(f"{t}: probe real={probe_all[t].get('real')} shuf={probe_all[t].get('shuffled_p95')}")
    valid = [t for t in TASKS if not probe_all[t].get("skipped")]
    mean_acc = {L: float(np.mean([probe_all[t]["real"][str(L)] for t in valid])) for L in LAYERS} if valid else {}
    if mean_acc:
        best = max(mean_acc.values())
        L_star = min(L for L in LAYERS if mean_acc[L] >= best - 1e-12)
    else:
        L_star = 20
    li_star = LAYERS.index(L_star)
    summary.update(L_star=L_star, probe=probe_all, probe_mean_acc=mean_acc,
                   per_task_argmax={t: max(probe_all[t]["real"], key=probe_all[t]["real"].get)
                                    for t in valid})
    logger.info(f"L* = {L_star} (mean balanced acc {mean_acc})")

    for t in TASKS:
        labs, acts = data[t]
        classes = taxonomy(t)
        labels = np.array([r["label"] for r in labs])
        forced_raw = {}
        forced_info = {}
        for c in bannable(t):
            p = DATA / "labels" / t / f"forced_{c}.jsonl"
            if not p.exists():
                continue
            fl, fa = load_cond(t, f"forced_{c}")
            fm = np.array([r["label"] == c for r in fl])
            use = fm if fm.sum() >= 3 else np.ones(len(fl), bool)
            forced_raw[c] = dict(window=fa["window"][use].astype(np.float32),
                                 precommit=fa["precommit"][use].astype(np.float32))
            forced_info[c] = dict(n=int(len(fl)), n_compliant=int(fm.sum()), used_compliant_only=bool(fm.sum() >= 3))
        out_npz = {}
        S_info = {}
        for pooling in ("window", "precommit"):
            X_all = acts[pooling].astype(np.float32)
            for li, L in enumerate(LAYERS):
                X = X_all[:, li]
                ok = ~np.isnan(X[:, 0])
                mu = X[ok].mean(0)
                fr = {c: v[pooling][:, li][~np.isnan(v[pooling][:, li, 0])] for c, v in forced_raw.items()}
                C, src = centroids(t, X[ok], labels[ok], fr, mu, classes)
                Cf, srcf = centroids(t, X[ok], labels[ok], fr, mu, classes, forced_only=True)
                out_npz[f"{pooling}_L{L}_C"] = C.astype(np.float32)
                out_npz[f"{pooling}_L{L}_S"] = cos_matrix(C)
                out_npz[f"{pooling}_L{L}_Sforced"] = cos_matrix(Cf)
                out_npz[f"{pooling}_L{L}_mu"] = mu
                if pooling == "window":
                    S_info[str(L)] = dict(source=src)
        # stability + natural-vs-forced agreement (window pooling)
        stab = {}
        nat_forced = {}
        Xw = acts["window"].astype(np.float32)
        for li, L in enumerate(LAYERS):
            stab[str(L)] = split_half(Xw[:, li], labels, classes)
            S = out_npz[f"window_L{L}_S"]
            Sf = out_npz[f"window_L{L}_Sforced"]
            src = S_info[str(L)]["source"]
            both = [k for k in range(len(classes)) if src[k] == "natural" and not np.isnan(Sf[k, k])]
            nat_forced[str(L)] = (dict(n_classes=len(both), spearman=float(spearmanr(offdiag(S, both),
                                       offdiag(Sf, both)).statistic)) if len(both) >= 3 else dict(n_classes=len(both)))
        # behavioural + lexical
        lists = [parse_list_names(r["output_text"], TASK_KIND[t]) for r in load_jsonl(GEN / t / "comention.jsonl")]
        beh = behavioural_S(lists, classes)
        out_npz["S_beh_rank"] = beh["rank"]
        out_npz["S_beh_pmi"] = beh["pmi"]
        out_npz["S_lex"] = lexical_S(classes)
        S_star = out_npz[f"window_L{L_star}_S"]
        nn = {}
        for b, cb in enumerate(classes):
            if np.isnan(S_star[b, b]):
                continue
            cand = [(S_star[b, k], classes[k]) for k in range(len(classes)) if k != b and not np.isnan(S_star[k, k])]
            if cand:
                nn[cb] = max(cand)[1]
        np.savez(GEO / f"geometry_{t}.npz", classes=np.array(classes), **out_npz)
        cnt = Counter(labels)
        summary["tasks"][t] = dict(
            classes=classes, counts=dict(cnt), forced=forced_info,
            centroid_source_Lstar=S_info[str(L_star)]["source"], S_Lstar=np.round(S_star, 4).tolist(),
            S_beh_rank=np.round(beh["rank"], 4).tolist(), S_lex=np.round(out_npz["S_lex"], 4).tolist(),
            stability=stab, natural_vs_forced=nat_forced, NN_Lstar=nn,
            comention_n_lists=len(lists),
            comention_doc_freq=dict(Counter(c for l in lists for c in set(l))),
            fallback_rate=float(acts["fallback"].mean()))
        logger.info(f"{t}: NN={nn} stability@L*={stab[str(L_star)]}")
    (GEO / "geometry.json").write_text(json.dumps(summary, indent=1, default=float))
    logger.info("geometry done")


if __name__ == "__main__":
    main()
