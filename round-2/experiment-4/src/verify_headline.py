#!/usr/bin/env python3
"""Independent re-derivation of the headline numbers from RAW files through a different code path
(no import of the analysis modules; own WLS, own kappa, own counting), plus shuffled/placebo controls that must FAIL.
Writes results/verify_headline.json.
"""
from __future__ import annotations

import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
R = ROOT / "results"


def rj(p):
    with open(p) as f:
        return [json.loads(x) for x in f if x.strip()]


def kappa(a, b):
    cats = sorted(set(a) | set(b))
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[c] * cb[c] for c in cats) / n / n
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def wls(x, y, w):
    X = np.column_stack([np.ones_like(x), x]) * np.sqrt(w)[:, None]
    beta, *_ = np.linalg.lstsq(X, y * np.sqrt(w), rcond=None)
    yhat = beta[0] + beta[1] * x
    ybar = np.sum(w * y) / np.sum(w)
    return beta, 1 - np.sum(w * (y - yhat) ** 2) / np.sum(w * (y - ybar) ** 2)


out = {}
lab = {r["id"]: r for r in rj(R / "labels_unified.jsonl")}

# 1. ban relabel: stored iteration-1 label files vs unified ledger
stored = []
for p in sorted((ROOT / "inputs/ban/labels").glob("*/*.jsonl")):
    for s in rj(p):
        stored.append((f"ban|{s['task']}|{s['condition']}|0.7|-1|{s['seed']}|{s['seed']}", s["label"]))
out["ban_relabel_identical"] = f"{sum(lab[i]['label'] == l for i, l in stored)}/{len(stored)}"
out["T1_baseline_counts_from_stored_files"] = dict(Counter(l for i, l in stored if "|T1|baseline|" in i))

# 2. C3 greedy flip rates straight from the gens files + ledger labels (unseeded = majority of 5 redraw greedy)
flip = {}
for t in ("T1", "T2", "T3"):
    reps = [lab[r["id"]]["label"] for r in rj(ROOT / "gens/redraw.jsonl") if r["task"] == t and r["cond"] == "greedy"]
    ug = Counter(reps).most_common(1)[0][0]
    gl = [lab[r["id"]]["label"] for r in rj(ROOT / "gens/seeds_fresh.jsonl")
          if r["task"] == t and r["cond"] == "seed_greedy"]
    flip[t] = dict(unseeded=ug, repeats=reps, flips=sum(x != ug for x in gl), n=len(gl),
                   rate=sum(x != ug for x in gl) / len(gl))
out["c3_greedy_flip"] = flip
c3 = json.loads((R / "c3_scoring.json").read_text())
out["c3_match_pipeline"] = {t: abs(flip[t]["rate"] - c3["tasks"][t]["observed_flip_rate"]) < 1e-12 for t in flip}

# 2b. placebo for the between-string heterogeneity test: shuffle samples across strings (destroys string identity);
#     re-run a simple chi-square-over-strings statistic and its permutation p — must be non-significant.
rng = random.Random(0)
s7 = defaultdict(list)
for r in rj(ROOT / "gens/seeds_fresh.jsonl"):
    if r["task"] == "T2" and r["cond"] == "seed_t07":
        s7[r["seed_string"]].append(lab[r["id"]]["label"])


def chi_stat(groups):
    labs = sorted({x for g in groups for x in g})
    T = np.array([[g.count(c) for c in labs] for g in groups], float)
    E = T.sum(1, keepdims=True) * T.sum(0, keepdims=True) / T.sum()
    return float(((T - E) ** 2 / np.where(E > 0, E, 1)).sum())


def perm_p(groups, n=2000):
    flat = [x for g in groups for x in g]
    obs = chi_stat(groups)
    ge = 0
    for _ in range(n):
        rng.shuffle(flat)
        it = iter(flat)
        ge += chi_stat([[next(it) for _ in g] for g in groups]) >= obs - 1e-9
    return (ge + 1) / (n + 1)


groups = list(s7.values())
flat = [x for g in groups for x in g]
rng.shuffle(flat)
it = iter(flat)
shuffled = [[next(it) for _ in g] for g in groups]
out["T2_heterogeneity_perm_p_real"] = perm_p(groups)
out["T2_heterogeneity_perm_p_shuffled_placebo"] = perm_p(shuffled)

# 3. C1: screen WLS line T2|-1 for every eligible idea, recounted from the ledger; T-shuffled placebo
fz = json.loads((R / "frozen_c1_temperature.json").read_text())["body"]["lines"]
TEMPS = [0.3, 0.5, 0.7, 1.0, 1.3, 1.6]
c1 = {}
for key, fr in fz.items():
    task, topk = key.split("|")
    rows = [r for r in lab.values() if r["source"] == "grid" and r["cond"] == "grid" and r["task"] == task
            and r["topk"] == int(topk)]
    by = {T: Counter(r["label"] for r in rows if r["T"] == T) for T in TEMPS}
    m = fr["reference"]
    x = 1 / np.array(TEMPS)
    res = {}
    for j in fr["eligible"]:
        cj = np.array([by[T][j] for T in TEMPS], float)
        cm = np.array([by[T][m] for T in TEMPS], float)
        (a, b), r2 = wls(x, np.log((cj + .5) / (cm + .5)), 1 / (1 / (cj + .5) + 1 / (cm + .5)))
        res[j] = dict(a=a, b=b, r2=r2, frozen_b=fr["lines"][j]["b"], frozen_r2=fr["lines"][j]["r2"],
                      match=abs(b - fr["lines"][j]["b"]) < 1e-6)
    # placebo: shuffle T labels across the task's rows -> slopes should collapse toward 0
    Ts = [r["T"] for r in rows]
    random.Random(1).shuffle(Ts)
    byp = defaultdict(Counter)
    for r, T in zip(rows, Ts):
        byp[T][r["label"]] += 1
    plac = {}
    for j in fr["eligible"]:
        cj = np.array([byp[T][j] for T in TEMPS], float)
        cm = np.array([byp[T][m] for T in TEMPS], float)
        (a, b), r2 = wls(x, np.log((cj + .5) / (cm + .5)), 1 / (1 / (cj + .5) + 1 / (cm + .5)))
        plac[j] = dict(b=b, r2=r2)
    c1[key] = dict(real=res, T_shuffled_placebo=plac)
out["c1_wls"] = c1

# 4. OOS MAE of the frozen anchored law vs the fixed-utility baseline, recomputed from raw redraw labels
p1 = json.loads((R / "frozen_c1_temperature.json").read_text())["body"]["p1_baseline_counts"]
oos = {}
for key, fr in fz.items():
    task, topk = key.split("|")
    m, el = fr["reference"], fr["eligible"]
    cls = [m] + el + ["rest"]

    def cnt(c, k):
        return sum(v for kk, v in c.items() if kk not in el and kk != m) if k == "rest" else c.get(k, 0)
    s = np.array([cnt(p1[task], k) + .5 for k in cls])
    b = np.array([0] + [fr["lines"][j]["b"] for j in el] + [fr["lines"]["__rest__"]["b"]])
    errs, errs_b = [], []
    for T in TEMPS:
        if T == 0.7:
            continue
        rows = [r["label"] for r in lab.values() if r["source"] == "redraw" and r["cond"] == "grid"
                and r["task"] == task and r["topk"] == int(topk) and r["T"] == T]
        c = Counter(rows)
        o = np.array([cnt(c, k) for k in cls]) / len(rows)
        lg = np.log(s / s[0]) - b / 0.7 + b / T
        p = np.exp(lg - lg.max()); p /= p.sum()
        lb = np.log(s / s.sum()) * 0.7 / T
        q = np.exp(lb - lb.max()); q /= q.sum()
        errs += list(np.abs(p - o)); errs_b += list(np.abs(q - o))
    oos[key] = dict(mae_frozen_anchored=float(np.mean(errs)), mae_fixed_utility=float(np.mean(errs_b)))
out["c1_oos_mae"] = oos

# 5. judge kappa from raw judge answers; shuffled-label placebo
raw = rj(R / "judge_raw.jsonl")
jl = defaultdict(dict)
for x in raw:
    if x["label"] is not None:
        jl[x["id"]][x["judge"]] = x["label"]
ids = [i for i, d in jl.items() if len(d) == 2 and i in lab]
j1 = [jl[i]["openai/gpt-4.1-mini"] for i in ids]
j2 = [jl[i]["google/gemini-2.5-flash-lite"] for i in ids]
v1 = [lab[i]["label"] for i in ids]
sh = v1[:]
random.Random(2).shuffle(sh)
out["judge"] = dict(n=len(ids), kappa_v1_j1=kappa(v1, j1), kappa_j1_j2=kappa(j1, j2), kappa_shuffled_v1_j1=kappa(sh, j1),
                    spend_usd=sum(x["cost"] for x in raw))

# 6. truncation flip rate from raw continuation file (reclassify prefix+continuation with the frozen classifier)
import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "src"))
from classify import classify_text  # noqa: E402
cont = rj(ROOT / "gens/trunc_cont.jsonl")
fl = [classify_text(r["prefix_text"] + r["text"], "sort" if r["task"] == "T2" else "graph")["label"]
      != lab[r["id"].replace("trunc|", "grid|", 1)]["label"] for r in cont]
out["truncation_flip"] = f"{sum(fl)}/{len(fl)} = {sum(fl) / len(fl):.3f}"

# 7. Hill/Leinster-Cobbold synthetic sanity (T8), own implementation
def lc_d1(Z):
    return math.exp(-np.log(Z.mean(1)).mean())
out["T8_LC_identical_eq_1"] = lc_d1(np.ones((10, 10)))
out["T8_LC_distinct_eq_10"] = lc_d1(np.eye(10))

(R / "verify_headline.json").write_text(json.dumps(out, indent=1, default=float))
print(json.dumps({k: v for k, v in out.items() if k != "c1_wls"}, indent=1, default=float)[:3500])
for k, v in c1.items():
    print(k, {j: (round(x["b"], 3), round(x["r2"], 3), x["match"]) for j, x in v["real"].items()},
          "placebo:", {j: (round(x["b"], 3), round(x["r2"], 3)) for j, x in v["T_shuffled_placebo"].items()})
