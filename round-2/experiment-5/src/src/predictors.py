"""Shared predictor machinery (screen fit, frozen prediction, confirmation scoring).

Every predictor shares: the smoothing floor Ptil0 (eps x co-mention share q), the compliance model
(banned mass = kappa_L x Ptil0(B), split within B proportional to Ptil0) and ONE fitted scalar that reweights
the unbanned mass:
  A  IIA         w_j = Ptil0(j)
  B  DISP        w_j = Ptil0(j) exp(beta s_j),  s_j = <Delta_b, c_j/|c_j|> / median screen ||Delta||
  C  NESTED      w_j = Ptil0(j) (1 + lam sum_{b in B} S_jb Ptil0(b) / max(Ptil0(B), 1e-3))   (iteration 1)
  D  EMBED       s_j = mean_{b in B} cos(e_j, e_b) - mean_k cos(e_j, e_k)   (bge names + descriptions)
  D2 EMBED-PROMPT s_j = <e(ban prompt) - e(placebo prompt), e_j/|e_j|> / median screen norm
  D3 LEXICAL     same form as D with Qwen input-embedding name vectors
  E  COMENTION   s_j = sum_{b in B} S_pmi[j, b]
"""
from __future__ import annotations

import re

import numpy as np

EPS_GRID = [0.5, 1.0, 2.0, 5.0, 10.0]
BETA_GRID = np.round(np.arange(-20, 20.0001, 0.25), 2)
PREDICTORS = ["A", "B", "C", "D", "D2", "D3", "E"]
EXP_FORM = {"B", "D", "D2", "D3", "E"}


def bucket(L: int) -> str:
    return "1" if L == 1 else ("2-3" if L <= 3 else "5")


def jsd(p: np.ndarray, q: np.ndarray) -> float:
    p = np.asarray(p, float)
    q = np.asarray(q, float)
    m = 0.5 * (p + q)

    def kl(a, b):
        mask = a > 0
        return float(np.sum(a[mask] * np.log2(a[mask] / b[mask])))

    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def floor_P0(counts0: np.ndarray, q: np.ndarray, eps: float) -> np.ndarray:
    return (counts0 + eps * q) / (counts0.sum() + eps)


def assemble(Pt0: np.ndarray, B: list[int], w: np.ndarray, kappa: float) -> np.ndarray:
    K = len(Pt0)
    P = np.zeros(K)
    pb = Pt0[B].sum()
    m_B = float(min(kappa * pb, 0.99))
    P[B] = m_B * Pt0[B] / max(pb, 1e-12)
    unb = np.ones(K, bool)
    unb[B] = False
    wu = np.clip(w[unb], 1e-300, None)
    P[unb] = (1 - m_B) * wu / wu.sum()
    return P


def weights(kind: str, Pt0: np.ndarray, B: list[int], param: float, s: np.ndarray | None,
            S: np.ndarray | None = None) -> np.ndarray:
    if kind == "A":
        return Pt0.copy()
    if kind == "C":
        sb = np.nan_to_num(S[:, B]) @ Pt0[B] / max(Pt0[B].sum(), 1e-3)
        return Pt0 * np.clip(1 + param * sb, 1e-6, None)
    z = np.clip(param * np.nan_to_num(s), -60, 60)
    return Pt0 * np.exp(z)


def predict(kind: str, item: dict, eps: float, kappa: dict, param: float) -> np.ndarray:
    Pt0 = floor_P0(item["counts0"], item["q"], eps)
    k = kappa.get(bucket(len(item["B"])), kappa["all"])
    w = weights(kind, Pt0, item["B"], param, item["s"].get(kind), item.get("S"))
    return assemble(Pt0, item["B"], w, k)


def fit_kappa(items: list[dict], eps: float) -> dict:
    num: dict[str, float] = {}
    den: dict[str, float] = {}
    for it in items:
        Pt0 = floor_P0(it["counts0"], it["q"], eps)
        b = bucket(len(it["B"]))
        obs = it["counts"][it["B"]].sum() / it["counts"].sum()
        num[b] = num.get(b, 0) + obs
        den[b] = den.get(b, 0) + Pt0[it["B"]].sum()
        num["all"] = num.get("all", 0) + obs
        den["all"] = den.get("all", 0) + Pt0[it["B"]].sum()
    return {b: num[b] / max(den[b], 1e-9) for b in num}


def param_grid(kind: str, items: list[dict]) -> np.ndarray:
    if kind == "A":
        return np.array([0.0])
    if kind == "C":
        smax = max(float(np.nanmax(np.abs(np.nan_to_num(it["S"])))) for it in items) or 1.0
        lo = -0.99 / smax
        return np.unique(np.round(np.concatenate([np.linspace(lo, 0, 41), np.linspace(0, 20, 81)]), 4))
    return BETA_GRID


def mean_jsd(kind: str, items: list[dict], eps: float, kappa: dict, param: float) -> float:
    return float(np.mean([jsd(predict(kind, it, eps, kappa, param), it["counts"] / it["counts"].sum())
                          for it in items]))


def fit_param(kind: str, items: list[dict], eps: float, kappa: dict) -> float:
    grid = param_grid(kind, items)
    scores = [mean_jsd(kind, items, eps, kappa, g) for g in grid]
    best = float(np.min(scores))
    cands = [g for g, s in zip(grid, scores) if s <= best + 1e-12]
    return float(min(cands, key=abs))  # ties -> smallest |param|


def fit_eps(items: list[dict]) -> float:
    """eps by LOBO mean JSD of IIA (no other parameter); then shared by every predictor."""
    best, best_e = None, None
    for e in EPS_GRID:
        js = []
        for i, it in enumerate(items):
            tr = items[:i] + items[i + 1:]
            kap = fit_kappa(tr, e)
            js.append(jsd(predict("A", it, e, kap, 0.0), it["counts"] / it["counts"].sum()))
        m = float(np.mean(js))
        if best is None or m < best - 1e-12:
            best, best_e = m, e
    return best_e


# ------------------------------------------------------------------------------------------------- metrics
def metrics_one(P_hat: np.ndarray, it: dict, eps: float) -> dict:
    n = it["counts"].sum()
    P_obs = it["counts"] / n
    P0 = it["counts0"] / it["counts0"].sum()
    Pt0 = floor_P0(it["counts0"], it["q"], eps)
    K = len(P_hat)
    unb = np.ones(K, bool)
    unb[it["B"]] = False
    pu_hat = P_hat[unb] / P_hat[unb].sum()
    pu_obs = P_obs[unb] / max(P_obs[unb].sum(), 1e-12)
    ll = float(np.sum(it["counts"] * np.log(np.clip(P_hat, 1e-12, None))) / n)
    gain_obs = np.where(unb, P_obs - P0, -np.inf)
    gain_hat = np.where(unb, P_hat - P0, -np.inf)
    top = None
    if np.max(gain_obs) >= 0.05:
        top = bool(int(np.argmax(gain_hat)) == int(np.argmax(gain_obs)))
    cells = []
    for j in np.where(unb)[0]:
        ch = P_obs[j] - P0[j]
        if abs(ch) >= 0.10:
            cells.append((int(np.sign(ch)), int(np.sign(P_hat[j] - Pt0[j]))))
    return dict(jsd=jsd(P_hat, P_obs), jsd_unbanned=jsd(pu_hat, pu_obs) if P_obs[unb].sum() > 0 else None,
                loglik=ll, top_hit=top, sign_cells=cells)


def summarize(per: list[dict]) -> dict:
    cells = [c for m in per for c in m["sign_cells"]]
    gains = [c for c in cells if c[0] > 0]
    losses = [c for c in cells if c[0] < 0]
    acc = float(np.mean([o == p for o, p in cells])) if cells else None
    accg = float(np.mean([o == p for o, p in gains])) if gains else None
    accl = float(np.mean([o == p for o, p in losses])) if losses else None
    bal = float(np.mean([x for x in (accg, accl) if x is not None])) if (gains or losses) else None
    tops = [m["top_hit"] for m in per if m["top_hit"] is not None]
    ju = [m["jsd_unbanned"] for m in per if m["jsd_unbanned"] is not None]
    return dict(n_bans=len(per), mean_jsd=float(np.mean([m["jsd"] for m in per])),
                mean_jsd_unbanned=float(np.mean(ju)) if ju else None,
                mean_loglik=float(np.mean([m["loglik"] for m in per])),
                top_hit_rate=float(np.mean(tops)) if tops else None, n_top=len(tops),
                sign_acc=acc, sign_acc_gain=accg, sign_acc_loss=accl, balanced_sign_acc=bal, n_sign_cells=len(cells),
                n_gain_cells=len(gains), n_loss_cells=len(losses))


# ------------------------------------------------------------------------------------------------- s-vectors
def unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def s_disp(delta: np.ndarray, C: np.ndarray, norm: float) -> np.ndarray:
    """C: [K, d] with NaN rows for classes without a centroid (s=0)."""
    s = np.zeros(C.shape[0])
    for j in range(C.shape[0]):
        if not np.isnan(C[j, 0]) and np.linalg.norm(C[j]) > 0:
            s[j] = float(delta @ unit(C[j])) / norm
    return s


def s_sim(S: np.ndarray, B: list[int], valid: np.ndarray) -> np.ndarray:
    """mean_{b in B} S[j,b] - mean_k S[j,k] over valid classes; 0 for invalid rows."""
    s = np.zeros(S.shape[0])
    vk = np.where(valid)[0]
    for j in vk:
        s[j] = float(np.nanmean(S[j, B])) - float(np.nanmean(S[j, vk]))
    return np.nan_to_num(s)


LEXICON_SELECT = [
    ("Median_of_medians", r"median"), ("Quickselect", r"quick\s*-?\s*select|hoare|randomi[sz]ed select|introselect"),
    ("Binary_search_value", r"binary search"), ("Heap_select", r"heap|priority"),
    ("Counting_bucket", r"counting|bucket|radix|frequency"),
    ("Partial_selection", r"selection sort|partial|repeated min|min\w*\s*extraction|linear scan"),
    ("Sort_index", r"sort"), ("Builtin", r"numpy|built-?in|nsmallest|statistics|pandas"),
]


def parse_select_list(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)[\.\):]\s*(.+)", line)
        if not m:
            continue
        cls = "Other"
        for c, pat in LEXICON_SELECT:
            if re.search(pat, m.group(2), re.I):
                cls = c
                break
        out.append(cls)
    return out
