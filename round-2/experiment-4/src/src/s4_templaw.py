#!/usr/bin/env python3
"""STEP 4: temperature law (claim C1) on a temperature grid (screen: source=grid; confirmation: source=redraw).

Per (task, T, topk) cell: shares (Wilson), entropy (bootstrap), Hill D0/D1/D2, rarefied E[S_10], Chao1, pass rate.
Arrhenius lines: y = ln((c_j+.5)/(c_m+.5)) vs x = 1/T, WLS (pre-registered R^2 >= 0.85) + quadratic AICc;
primary inference = multinomial logit (statsmodels MNLogit) on raw counts with x and x^2 (LR curvature test) and
intercepts a_j (H0 a_j = 0 = pure scale-parameter / fixed-utility logit).
Rank reversals among the top-3 at T=1; Hill alpha (within-idea phrasing diversity, similarity-sensitive,
rarefied m=8) vs idea-level D1; the user's (a)/(b)/(c) table on 10-sample draws; correctness vs T; repro rows;
a simulation calibrating R^2 and the LR test under a TRUE linear law.

Usage: s4_templaw.py --source grid   -> results/temperature_law_screen.json
       s4_templaw.py --source redraw -> results/temperature_law_redraw.json (+ out-of-sample scoring vs frozen C1)
"""
from __future__ import annotations

import argparse
import math
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (GENS, LABELS_PATH, NON_IDEAS, ORACLE_PATH, RESULTS, TEMPS, canonical_sha, chao1,  # noqa: E402
                    entropy_bits, entropy_ci, hill, jsd_bits, load_json, normalise_code_tokens, rarefied_richness,
                    read_jsonl, save_json, setup_logging, wilson)

warnings.filterwarnings("ignore")
ALPHA_M = 8          # programs per idea in each rarefied draw
ALPHA_DRAWS = 50
PHRASE_SIM = 0.85    # Z1 threshold for 'same phrasing' (single linkage)
ABC_DRAWS = 200
N_BOOT_R = 300


def load_rows(source: str) -> list[dict]:
    orc = {r["id"]: r for r in read_jsonl(ORACLE_PATH)}
    rows = [r for r in read_jsonl(LABELS_PATH) if r["source"] == source]
    for r in rows:
        o = orc.get(r["id"])
        r["pass"] = None if o is None else bool(o["passed"])
        r["oracle_status"] = None if o is None else o["status"]
    return rows


def cell_key(task, T, topk):
    return f"{task}|{T}|{topk}"


# ----------------------------------------------------------------------------- Arrhenius (WLS)
def wls_line(x: np.ndarray, y: np.ndarray, w: np.ndarray, quad: bool = False) -> dict:
    X = np.column_stack([np.ones_like(x), x] + ([x ** 2] if quad else []))
    W = np.diag(w)
    XtW = X.T @ W
    beta = np.linalg.solve(XtW @ X, XtW @ y)
    res = y - X @ beta
    n, k = len(y), X.shape[1]
    s2 = float(res @ W @ res) / max(n - k, 1)
    cov = s2 * np.linalg.inv(XtW @ X)
    ybar = float((w * y).sum() / w.sum())
    sst = float((w * (y - ybar) ** 2).sum())
    r2 = 1 - float((w * res ** 2).sum()) / sst if sst > 0 else float("nan")
    # Gaussian log-lik with known weights up to constant -> AICc
    rss = float((w * res ** 2).sum())
    ll = -0.5 * n * (math.log(2 * math.pi * rss / n) + 1)
    kk = k + 1
    aicc = -2 * ll + 2 * kk + (2 * kk * (kk + 1)) / max(n - kk - 1, 1e-9) if n - kk - 1 > 0 else float("nan")
    return dict(coef=beta.tolist(), se=np.sqrt(np.diag(cov)).tolist(), r2=r2, aicc=aicc)


def arrhenius_lines(cells: dict, task: str, topk: int) -> dict:
    """cells[(T)] = Counter of labels. Returns reference, eligible lines with WLS fits."""
    c1 = cells.get(1.0)
    if c1 is None:
        return dict(error="no T=1.0 cell")
    n1 = sum(c1.values())
    ideas1 = {k: v for k, v in c1.items() if k not in NON_IDEAS}
    m = max(ideas1, key=lambda k: (ideas1[k], k))
    elig = sorted([k for k, v in ideas1.items() if k != m and v / n1 >= 0.03], key=lambda k: -c1[k])
    temps = sorted(cells)
    x = np.array([1 / T for T in temps])
    lines = {}
    for j in elig + ["__rest__"]:
        if j == "__rest__":
            cj = np.array([sum(v for k, v in cells[T].items() if k not in elig and k != m) for T in temps], float)
        else:
            cj = np.array([cells[T].get(j, 0) for T in temps], float)
        cm = np.array([cells[T].get(m, 0) for T in temps], float)
        y = np.log((cj + 0.5) / (cm + 0.5))
        w = 1 / (1 / (cj + 0.5) + 1 / (cm + 0.5))
        lin = wls_line(x, y, w)
        quad = wls_line(x, y, w, quad=True)
        ns = np.array([sum(cells[T].values()) for T in temps], float)
        underpowered = bool(np.any(cj < 5))
        lines[j] = dict(a=lin["coef"][0], b=lin["coef"][1], a_se=lin["se"][0], b_se=lin["se"][1], r2=lin["r2"],
                        aicc_lin=lin["aicc"], aicc_quad=quad["aicc"],
                        d_aicc_quad_minus_lin=(quad["aicc"] - lin["aicc"]) if np.isfinite(quad["aicc"]) else None,
                        quad_coef=quad["coef"], counts=cj.tolist(), mode_counts=cm.tolist(), n=ns.tolist(),
                        y=y.tolist(), x=x.tolist(), underpowered=underpowered,
                        intercept_z=lin["coef"][0] / lin["se"][0] if lin["se"][0] > 0 else None)
    return dict(reference=m, eligible=elig, temps=temps, lines=lines)


def mnlogit_tests(rows_by_T: dict, m: str, elig: list[str]) -> dict:
    """Baseline-category multinomial logit on raw counts: linear vs quadratic in x=1/T; intercepts with CI."""
    import statsmodels.api as sm
    from scipy import stats
    cats = [m] + elig
    y, x = [], []
    for T, labs in rows_by_T.items():
        for lab in labs:
            if lab in cats:
                y.append(cats.index(lab))
                x.append(1 / T)
    y, x = np.array(y), np.array(x)
    out = {}
    try:
        X1 = sm.add_constant(np.column_stack([x]))
        X2 = sm.add_constant(np.column_stack([x, x ** 2]))
        f1 = sm.MNLogit(y, X1).fit(disp=0, maxiter=500, method="newton")
        f2 = sm.MNLogit(y, X2).fit(disp=0, maxiter=500, method="newton")
        lr = 2 * (f2.llf - f1.llf)
        df = len(elig)
        out["lr_curvature"] = dict(LR=float(lr), df=df, p=float(stats.chi2.sf(lr, df)))
        p1, b1 = np.asarray(f1.params), np.asarray(f1.bse)
        out["linear"] = {}
        for k, j in enumerate(elig):
            a, b = float(p1[0, k]), float(p1[1, k])
            sa, sb = float(b1[0, k]), float(b1[1, k])
            out["linear"][j] = dict(a=a, a_ci=[a - 1.96 * sa, a + 1.96 * sa], a_p=float(2 * stats.norm.sf(abs(a / sa)))
                                    if sa > 0 else None, b=b, b_ci=[b - 1.96 * sb, b + 1.96 * sb])
        out["n_rows"] = int(len(y))
        out["converged"] = bool(f1.mle_retvals.get("converged", True)) and bool(f2.mle_retvals.get("converged", True))
    except (np.linalg.LinAlgError, ValueError, ZeroDivisionError) as e:
        out["error"] = repr(e)[:200]
    # pairwise binomial GLMs (robust fallback; also per-line LR)
    pair = {}
    for j in elig:
        sel = np.isin(y, [0, cats.index(j)])
        if sel.sum() < 10:
            continue
        yy = (y[sel] == cats.index(j)).astype(float)
        xx = x[sel]
        try:
            g1 = sm.GLM(yy, sm.add_constant(xx), family=sm.families.Binomial()).fit()
            g2 = sm.GLM(yy, sm.add_constant(np.column_stack([xx, xx ** 2])), family=sm.families.Binomial()).fit()
            lr = 2 * (g2.llf - g1.llf)
            pair[j] = dict(a=float(g1.params[0]), a_se=float(g1.bse[0]), b=float(g1.params[1]),
                           b_se=float(g1.bse[1]), lr_curv=float(lr), p_curv=float(stats.chi2.sf(lr, 1)))
        except (np.linalg.LinAlgError, ValueError) as e:
            pair[j] = dict(error=repr(e)[:120])
    out["pairwise_binomial"] = pair
    return out


def rank_reversals(rows_by_T: dict, top3: list[str], seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    out = {}
    for T, labs in rows_by_T.items():
        if T == 1.0:
            continue
        arr = np.asarray(labs)
        n = len(arr)
        c = Counter(labs)
        res = []
        for a in range(len(top3)):
            for b in range(a + 1, len(top3)):
                hi, lo = top3[a], top3[b]
                pa, pb = c.get(hi, 0) / n, c.get(lo, 0) / n
                rev = pb > pa
                boots = rng.integers(0, n, (2000, n))
                ba = (arr[boots] == hi).mean(1)
                bb = (arr[boots] == lo).mean(1)
                var = (pa + pb - (pa - pb) ** 2) / n
                z = (pb - pa) / math.sqrt(var) if var > 0 else 0.0
                from scipy import stats
                p_one = float(stats.norm.sf(z))
                res.append(dict(pair=[hi, lo], share_hi=pa, share_lo=pb, reversal=bool(rev),
                                boot_p_flip=float((bb > ba).mean()), z=z, p_one_sided=p_one,
                                significant=bool(rev and p_one < 0.05)))
        out[str(T)] = res
    return out


# ----------------------------------------------------------------------------- Hill alpha / phrasings
class Encoder:
    def __init__(self):
        self.vocab: dict[str, str] = {}

    def enc(self, toks: list[str]) -> str:
        out = []
        for t in toks:
            if t not in self.vocab:
                self.vocab[t] = chr(0x4E00 + len(self.vocab))
            out.append(self.vocab[t])
        return "".join(out)


def dist_matrix(strings: list[str]) -> np.ndarray:
    from rapidfuzz.distance import Levenshtein
    from rapidfuzz.process import cdist
    if not strings:
        return np.zeros((0, 0))
    d = cdist(strings, strings, scorer=Levenshtein.normalized_distance, workers=4, dtype=np.float32)
    return np.asarray(d, float)


def lc_d1_draws(Z: np.ndarray, idx_pool: np.ndarray, m: int, draws: int, rng) -> float:
    """Mean Leinster-Cobbold D1^Z over `draws` random m-subsets (uniform weights 1/m)."""
    if len(idx_pool) < m:
        return float("nan")
    vals = []
    for _ in range(draws):
        s = rng.choice(idx_pool, m, replace=False)
        sub = Z[np.ix_(s, s)]
        zp = sub.mean(1)
        vals.append(math.exp(-np.log(zp).mean()))
    return float(np.mean(vals))


def n_clusters(D: np.ndarray, thr: float) -> int:
    n = len(D)
    parent = list(range(n))

    def f(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    ii, jj = np.where(np.triu(D <= thr, 1))
    for a, b in zip(ii, jj):
        ra, rb = f(a), f(b)
        if ra != rb:
            parent[ra] = rb
    return len({f(i) for i in range(n)})


def distinct_4gram_ratio(texts: list[str]) -> float:
    tot, seen = 0, set()
    for t in texts:
        w = t.split()[:400]
        for i in range(len(w) - 3):
            g = tuple(w[i:i + 4])
            seen.add(g)
            tot += 1
    return len(seen) / tot if tot else float("nan")


def cell_alpha(labels: list[str], Z: np.ndarray, rng, draws: int = ALPHA_DRAWS, idx: np.ndarray | None = None):
    """alpha_1 = exp(sum_i p_i ln D_i) over ideas with n_i >= ALPHA_M (p renormalised)."""
    if idx is None:
        idx = np.arange(len(labels))
    lab = np.asarray(labels)[idx]
    per = {}
    for k in sorted(set(lab)):
        if k in NON_IDEAS:
            continue
        pos = idx[lab == k]
        if len(pos) >= ALPHA_M:
            per[k] = (len(pos), lc_d1_draws(Z, pos, ALPHA_M, draws, rng))
    if not per:
        return float("nan"), {}
    tot = sum(v[0] for v in per.values())
    la = sum(v[0] / tot * math.log(v[1]) for v in per.values())
    return math.exp(la), {k: dict(n=v[0], D1Z=v[1]) for k, v in per.items()}


def abc_cell(labels: list[str], D: np.ndarray, rng) -> dict:
    n = len(labels)
    e_ideas = rarefied_richness(Counter(labels).values(), 10)
    ncl = []
    for _ in range(ABC_DRAWS):
        s = rng.choice(n, min(10, n), replace=False)
        ncl.append(n_clusters(D[np.ix_(s, s)], 1 - PHRASE_SIM))
    e_phr = float(np.mean(ncl))
    verdict = "a" if (e_ideas <= 3 and e_phr >= 7) else ("b" if e_ideas >= 7 else "mixed")
    return dict(E_ideas_10=e_ideas, E_phrasings_10=e_phr, E_phrasings_per_idea=e_phr / e_ideas if e_ideas else None,
                verdict=verdict)


# ----------------------------------------------------------------------------- simulation (T9)
def simulate_linear_law(shares_T1: dict, m: str, elig: list[str], n_sim: int = 200, n: int = 100, seed: int = 0):
    import statsmodels.api as sm
    from scipy import stats
    rng = np.random.default_rng(seed)
    cats = list(shares_T1)
    u = np.log(np.array([max(shares_T1[c], 1e-4) for c in cats]))
    temps = np.array(TEMPS)
    x = 1 / temps
    r2_low = defaultdict(int)
    cover = defaultdict(int)
    rej = 0
    nvalid = 0
    for s in range(n_sim):
        counts = []
        for T in temps:
            p = np.exp(u / T - (u / T).max())
            p /= p.sum()
            counts.append(dict(zip(cats, rng.multinomial(n, p))))
        lr_tot, ok = 0.0, True
        for j in elig:
            cj = np.array([c[j] for c in counts], float)
            cm = np.array([c[m] for c in counts], float)
            y = np.log((cj + .5) / (cm + .5))
            w = 1 / (1 / (cj + .5) + 1 / (cm + .5))
            fit = wls_line(x, y, w)
            if fit["r2"] < 0.85:
                r2_low[j] += 1
            true_b = u[cats.index(j)] - u[cats.index(m)]
            if abs(fit["coef"][1] - true_b) <= 2 * fit["se"][1]:
                cover[j] += 1
            yy = np.concatenate([np.r_[np.ones(int(a)), np.zeros(int(b))] for a, b in zip(cj, cm)])
            xx = np.concatenate([np.full(int(a + b), xv) for a, b, xv in zip(cj, cm, x)])
            try:
                g1 = sm.GLM(yy, sm.add_constant(xx), family=sm.families.Binomial()).fit()
                g2 = sm.GLM(yy, sm.add_constant(np.column_stack([xx, xx ** 2])),
                            family=sm.families.Binomial()).fit()
                lr_tot += 2 * (g2.llf - g1.llf)
            except (np.linalg.LinAlgError, ValueError):
                ok = False
        if ok and elig:
            nvalid += 1
            rej += stats.chi2.sf(lr_tot, len(elig)) < 0.05
    return dict(n_sim=n_sim, frac_r2_below_085={j: r2_low[j] / n_sim for j in elig},
                slope_within_2se={j: cover[j] / n_sim for j in elig},
                lr_curvature_rejection_rate=rej / max(nvalid, 1), n_valid=nvalid,
                true_shares_T1=shares_T1)


# ----------------------------------------------------------------------------- main analysis
def analyse(source: str) -> dict:
    rows = [r for r in load_rows(source) if r["cond"] == "grid"]
    logger.info(f"{source}: {len(rows)} grid rows")
    progs = {p["id"]: p["code"] for p in read_jsonl(GENS / "programs.jsonl")}
    texts = {}
    enc = Encoder()
    strings = {r["id"]: enc.enc(normalise_code_tokens(progs.get(r["id"], ""))) for r in rows}
    out: dict = dict(source=source, cells={}, arrhenius={}, glm={}, reversals={}, hill={}, abc={}, correctness={},
                     simulation={})
    by = defaultdict(list)
    for r in rows:
        by[(r["task"], r["T"], r["topk"])].append(r)
    rng = np.random.default_rng(12345)
    Dcache = {}
    for (task, T, topk), rs in sorted(by.items()):
        rs = sorted(rs, key=lambda r: r["idx"])
        labs = [r["label"] for r in rs]
        cnt = Counter(labs)
        n = len(labs)
        h, hlo, hhi = entropy_ci(labs, 2000, seed=1)
        passes = [r["pass"] for r in rs if r["pass"] is not None]
        pw = wilson(sum(passes), len(passes)) if passes else (None, None, None)
        D = dist_matrix([strings[r["id"]] for r in rs])
        Dcache[(task, T, topk)] = (labs, D)
        a1, per_idea = cell_alpha(labs, 1 - D, rng)
        hl = hill([v for k, v in cnt.items() if k != "Unparseable"])
        out["cells"][cell_key(task, T, topk)] = dict(
            task=task, T=T, topk=topk, n=n, counts=dict(cnt.most_common()),
            shares={k: dict(zip(("p", "lo", "hi"), wilson(v, n))) for k, v in cnt.items()},
            entropy_bits=h, entropy_ci=[hlo, hhi], hill=hl, E_S10=rarefied_richness(cnt.values(), 10),
            chao1=chao1(cnt.values()), pass_rate=pw[0], pass_ci=[pw[1], pw[2]], n_oracle=len(passes),
            oracle_status=dict(Counter(r["oracle_status"] for r in rs)),
            trunc_rate=sum(r["finish_reason"] == "length" for r in rs) / n,
            alpha1=a1, alpha_per_idea=per_idea, lexical_distinct4=None)
    # lexical distinct-4gram (needs raw text; read from source files lazily)
    try:
        txt = load_texts(source)
        for (task, T, topk), rs in by.items():
            out["cells"][cell_key(task, T, topk)]["lexical_distinct4"] = distinct_4gram_ratio(
                [txt.get(r["id"], "") for r in rs])
    except (FileNotFoundError, KeyError) as e:
        logger.warning(f"lexical distinct-4 skipped: {e!r}")
    tasks = sorted({k[0] for k in by})
    topks = sorted({k[2] for k in by})
    for task in tasks:
        for topk in topks:
            cells = {T: Counter(r["label"] for r in by[(task, T, topk)]) for T in TEMPS if (task, T, topk) in by}
            if len(cells) < 3:
                continue
            key = f"{task}|{topk}"
            ar = arrhenius_lines(cells, task, topk)
            out["arrhenius"][key] = ar
            if "error" in ar:
                continue
            ar["excluded_F7"] = len(ar["eligible"]) < 1
            rows_by_T = {T: [r["label"] for r in by[(task, T, topk)]] for T in cells}
            if ar["eligible"]:
                out["glm"][key] = mnlogit_tests(rows_by_T, ar["reference"], ar["eligible"])
            c1 = cells[1.0]
            top3 = [k for k, _ in sorted(((k, v) for k, v in c1.items() if k not in NON_IDEAS),
                                         key=lambda kv: (-kv[1], kv[0]))][:3]
            out["reversals"][key] = dict(top3_T1=top3, by_T=rank_reversals(rows_by_T, top3))
            # Hill partition slopes
            Ts = sorted(cells)
            la = np.array([math.log(out["cells"][cell_key(task, T, topk)]["alpha1"])
                           if out["cells"][cell_key(task, T, topk)]["alpha1"] == out["cells"][cell_key(task, T, topk)]["alpha1"]
                           else np.nan for T in Ts])
            lb = np.array([math.log(out["cells"][cell_key(task, T, topk)]["hill"]["D1"]) for T in Ts])
            both = np.isfinite(la) & np.isfinite(lb)   # slopes over temperatures where both are defined
            sa, sb = _slope(np.asarray(Ts)[both], la[both]), _slope(np.asarray(Ts)[both], lb[both])
            boots = []
            brng = np.random.default_rng(7)
            for _ in range(N_BOOT_R):
                bla, blb = [], []
                for T in Ts:
                    labs, D = Dcache[(task, T, topk)]
                    idx = brng.integers(0, len(labs), len(labs))
                    a1, _ = cell_alpha(labs, 1 - D, brng, draws=8, idx=idx)
                    bla.append(math.log(a1) if a1 == a1 else np.nan)
                    blb.append(math.log(hill([v for k, v in Counter(np.asarray(labs)[idx].tolist()).items()
                                              if k != "Unparseable"])["D1"]))
                bla_, blb_ = np.array(bla), np.array(blb)
                bb_ = np.isfinite(bla_) & np.isfinite(blb_) & both
                s_a, s_b = _slope(np.asarray(Ts)[bb_], bla_[bb_]), _slope(np.asarray(Ts)[bb_], blb_[bb_])
                boots.append((s_a, s_b, s_a / s_b if s_b not in (0, None) and s_b == s_b else np.nan))
            boots = np.array(boots, float)

            def q(v):
                v = v[np.isfinite(v)]
                return [float(np.quantile(v, .025)), float(np.quantile(v, .975))] if len(v) > 10 else [None, None]
            ratio = sa / sb if sb not in (0, None) and sb == sb else float("nan")
            sb_ci = q(boots[:, 1])
            flat = sb_ci[0] is not None and sb_ci[0] <= 0 <= sb_ci[1]
            out["hill"][key] = dict(T=Ts, T_used=np.asarray(Ts)[both].tolist(), ln_alpha1=la.tolist(),
                                    ln_beta1=lb.tolist(), slope_alpha=sa,
                                    slope_alpha_ci=q(boots[:, 0]), slope_beta=sb, slope_beta_ci=sb_ci,
                                    ratio_R=None if flat else ratio, ratio_ci=q(boots[:, 2]),
                                    note="idea count flat: case (a)" if flat else "")
            # abc table
            out["abc"][key] = {}
            for T in Ts:
                labs, D = Dcache[(task, T, topk)]
                out["abc"][key][str(T)] = abc_cell(labs, D, rng)
            lo_T, hi_T = out["abc"][key][str(min(Ts))], out["abc"][key][str(max(Ts))]
            d_ideas = hi_T["E_ideas_10"] - lo_T["E_ideas_10"]
            d_ppi = (hi_T["E_phrasings_per_idea"] or 0) - (lo_T["E_phrasings_per_idea"] or 0)
            mid = out["abc"][key].get("1.3")
            if mid is not None:
                d_i13 = mid["E_ideas_10"] - lo_T["E_ideas_10"]
                d_p13 = (mid["E_phrasings_per_idea"] or 0) - (lo_T["E_phrasings_per_idea"] or 0)
                out["abc"][key]["c_verdict_0.3_to_1.3"] = dict(
                    delta_E_ideas=d_i13, delta_phrasings_per_idea=d_p13,
                    verdict="c-b (more ideas)" if d_i13 >= 1.5 else
                    ("c-a (few ideas, more phrasings each)" if d_p13 > 0 else "neither"))
            out["abc"][key]["c_verdict"] = dict(delta_E_ideas=d_ideas, delta_phrasings_per_idea=d_ppi,
                                                verdict="c-b (more ideas)" if d_ideas >= 1.5 else
                                                ("c-a (few ideas, more phrasings each)" if d_ppi > 0 else
                                                 "neither"))
            # simulation of the TRUE linear law at the observed T=1 shares
            if ar["eligible"] and source == "grid":
                n1 = sum(c1.values())
                out["simulation"][key] = simulate_linear_law({k: v / n1 for k, v in c1.items()}, ar["reference"],
                                                             ar["eligible"], n_sim=200, seed=3)
        # correctness ~ idea + T + topk
        out["correctness"][task] = correctness_glm([r for r in rows if r["task"] == task])
    # quality-diversity curves
    out["quality_diversity"] = {f"{t}|{k}": [dict(T=T, pass_rate=out["cells"][cell_key(t, T, k)]["pass_rate"],
                                                  entropy=out["cells"][cell_key(t, T, k)]["entropy_bits"])
                                             for T in TEMPS if cell_key(t, T, k) in out["cells"]]
                                for t in tasks for k in topks}
    if source == "grid":
        out["repro_rows"] = repro_rows()
    out["c1_criteria"] = c1_criteria(out)
    return out


def _slope(Ts, ys) -> float:
    Ts = np.asarray(Ts, float)
    ys = np.asarray(ys, float)
    ok = np.isfinite(ys)
    if ok.sum() < 3:
        return float("nan")
    return float(np.polyfit(Ts[ok], ys[ok], 1)[0])


def load_texts(source: str) -> dict:
    from common import INPUTS
    out = {}
    if source == "grid":
        for r in read_jsonl(INPUTS / "grid" / "data" / "raw_grid.jsonl"):
            out[f"grid|{r['task']}|{r['cond']}|{r['T']}|{r['topk']}|{r['seed']}|{r['sample_idx']}"] = r["text"]
    else:
        for p in GENS.glob("*.jsonl"):
            if p.name == "programs.jsonl":
                continue
            for r in read_jsonl(p):
                if r.get("source") == source:
                    out[r["id"]] = r["text"]
    return out


def correctness_glm(rows: list[dict]) -> dict:
    import pandas as pd
    import statsmodels.formula.api as smf
    d = pd.DataFrame([dict(p=int(r["pass"]), idea=r["label"], T=r["T"], topk=str(r["topk"])) for r in rows
                      if r["pass"] is not None])
    if len(d) < 50 or d["p"].nunique() < 2:
        return dict(n=len(d), error="insufficient oracle data")
    vc = d["idea"].value_counts()
    d["idea"] = d["idea"].where(d["idea"].map(vc) >= 15, "rare_pooled")
    ref = vc.index[0]
    try:
        f = smf.logit(f"p ~ C(idea, Treatment('{ref}')) + T + C(topk)", data=d).fit(disp=0, maxiter=200)
        return dict(n=len(d), reference_idea=ref, params={k: float(v) for k, v in f.params.items()},
                    pvalues={k: float(v) for k, v in f.pvalues.items()},
                    pass_by_idea={k: float(v) for k, v in d.groupby("idea")["p"].mean().items()})
    except (np.linalg.LinAlgError, ValueError) as e:
        return dict(n=len(d), error=repr(e)[:200],
                    pass_by_idea={k: float(v) for k, v in d.groupby("idea")["p"].mean().items()})


def repro_rows() -> dict:
    lab = {r["id"]: r for r in read_jsonl(LABELS_PATH) if r["source"] == "grid"}
    grid = {(r["task"], r["T"], r["topk"], r["idx"]): r["label"] for r in lab.values() if r["cond"] == "grid"}
    rep = [r for r in lab.values() if r["cond"] == "repeat"]
    same = [grid.get((r["task"], r["T"], r["topk"], r["idx"])) == r["label"] for r in rep]
    return dict(n=len(rep), identical_labels=int(sum(same)), identical_tokens_iter1="2/20",
                pairs=[dict(task=r["task"], T=r["T"], topk=r["topk"], idx=r["idx"], repeat=r["label"],
                            grid=grid.get((r["task"], r["T"], r["topk"], r["idx"]))) for r in rep])


def c1_criteria(out: dict) -> dict:
    res = {}
    for key, ar in out["arrhenius"].items():
        if "error" in ar or not ar["eligible"]:
            res[key] = dict(eligible=False, reason="F7: <2 ideas >= 3% at T=1")
            continue
        r2s = {j: ar["lines"][j]["r2"] for j in ar["eligible"]}
        rev = out["reversals"].get(key, {}).get("by_T", {})
        rev_le13 = [dict(T=T, **x) for T, lst in rev.items() if float(T) <= 1.3 for x in lst if x["reversal"]]
        h = out["hill"].get(key, {})
        ratio = h.get("ratio_R")
        res[key] = dict(eligible=True, r2=r2s, frac_r2_ge_085=float(np.mean([v >= 0.85 for v in r2s.values()])),
                        all_r2_ge_085=all(v >= 0.85 for v in r2s.values()),
                        reversals_T_le_13=rev_le13, no_reversal_T_le_13=len(rev_le13) == 0,
                        ratio_R=ratio, ratio_ci=h.get("ratio_ci"), ratio_ge_3=bool(ratio is not None and ratio >= 3),
                        lr_curvature=out["glm"].get(key, {}).get("lr_curvature"),
                        pass_all=bool(all(v >= 0.85 for v in r2s.values()) and len(rev_le13) == 0
                                      and ratio is not None and ratio >= 3))
    return res


# ----------------------------------------------------------------------------- out-of-sample scoring
def oos_scoring(redraw: dict) -> dict:
    fz = load_json(RESULTS / "frozen_c1_temperature.json")
    body = fz["body"]
    out = {}
    for key, fr in body["lines"].items():
        task, topk = key.split("|")
        m, elig = fr["reference"], fr["eligible"]
        anchor = body["p1_baseline_counts"][task]
        cls = [m] + elig + ["__rest__"]

        def cnt_of(c, k):
            if k == "__rest__":
                return sum(v for kk, v in c.items() if kk not in elig and kk != m)
            return c.get(k, 0)
        s07 = np.array([cnt_of(anchor, k) + 0.5 for k in cls], float)
        b = np.array([0.0] + [fr["lines"][j]["b"] for j in elig] + [fr["lines"]["__rest__"]["b"]])
        a_froz = np.array([0.0] + [fr["lines"][j]["a"] for j in elig] + [fr["lines"]["__rest__"]["a"]])
        a_anch = np.log(s07 / s07[0]) - b / 0.7
        p07 = s07 / s07.sum()
        res = dict(classes=cls, by_T={}, models={})
        preds = {"frozen_anchored": [], "frozen_unanchored": [], "baseline_fixed_utility": [],
                 "baseline_no_temperature_effect": []}
        obs_all = []
        for T in TEMPS:
            ck = cell_key(task, T, int(topk))
            if ck not in redraw["cells"]:
                continue
            c = redraw["cells"][ck]["counts"]
            n = sum(c.values())
            obs = np.array([cnt_of(c, k) for k in cls], float) / n
            mods = {}
            for name, logits in (("frozen_anchored", a_anch + b / T), ("frozen_unanchored", a_froz + b / T),
                                 ("baseline_fixed_utility", np.log(p07) * 0.7 / T),
                                 ("baseline_no_temperature_effect", np.log(p07))):
                p = np.exp(logits - logits.max())
                p /= p.sum()
                mods[name] = p
            res["by_T"][str(T)] = dict(observed=dict(zip(cls, obs.tolist())), n=n,
                                       **{f"pred_{k}": dict(zip(cls, v.tolist())) for k, v in mods.items()},
                                       **{f"jsd_{k}": jsd_bits(dict(zip(cls, obs)), dict(zip(cls, v)))
                                          for k, v in mods.items()})
            if abs(T - 0.7) > 1e-9:
                obs_all.append(obs)
                for k in preds:
                    preds[k].append(mods[k])
        if obs_all:
            O = np.concatenate(obs_all)
            for k, P in preds.items():
                P = np.concatenate(P)
                slope = float(np.polyfit(P, O, 1)[0]) if np.std(P) > 0 else None
                res["models"][k] = dict(mae=float(np.abs(P - O).mean()), calibration_slope=slope)
        # new top-3 reversals at T <= 1.3 relative to frozen screen order
        top3 = fr["top3_T1"]
        new_rev = []
        for T in TEMPS:
            ck = cell_key(task, T, int(topk))
            if T > 1.3 or T == 1.0 or ck not in redraw["cells"]:
                continue
            c = redraw["cells"][ck]["counts"]
            for i in range(len(top3)):
                for j in range(i + 1, len(top3)):
                    if c.get(top3[j], 0) > c.get(top3[i], 0):
                        new_rev.append(dict(T=T, pair=[top3[i], top3[j]]))
        res["reversals_vs_frozen_order_T_le_13"] = new_rev
        out[key] = res
    return dict(frozen_sha256=fz["sha256"], per_line=out)


@logger.catch(reraise=True)
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="grid", choices=["grid", "redraw"])
    args = ap.parse_args()
    setup_logging(f"s4_templaw_{args.source}")
    out = analyse(args.source)
    if args.source == "redraw":
        out["oos"] = oos_scoring(out)
        save_json(RESULTS / "temperature_law_redraw.json", out)
    else:
        save_json(RESULTS / "temperature_law_screen.json", out)
    for k, v in out["c1_criteria"].items():
        logger.info(f"C1 {args.source} {k}: {v}")
    logger.info(f"sha of output body: {canonical_sha(out)[:12]}")


if __name__ == "__main__":
    main()
