#!/usr/bin/env python3
"""STEP 3: ban-arm screen tables (P1 wording, T=0.7, n=100 per ban condition, n=300 baseline).

Counts, entropy (bootstrap CI), compliance (still-banned), pass (Wilson), oracle-status split, off-menu correct
share (P4 menus, recomputed and asserted), forced purity, co-mention similarity, Fisher/Holm regularity tests with a
replicate noise floor, wording robustness (para1/para2 vs ban_r1), and the grid-vs-P1 wording check.

NOTE: the ban arm's __topup files (seeds 100..199) do NOT exist in the iteration-1 workspace (only 4,210 programs,
not ~5,070). The replicate noise floor therefore comes from the baseline thirds (seeds 0..99 / 100..199 / 200..299,
n=100 each, same prompt) - the same n as each ban cell - and is reported as such.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np
from loguru import logger
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (INPUTS, LABELS_PATH, MENUS, NON_IDEAS, ORACLE_PATH, RARE_CORRECT, RESULTS, entropy_ci,  # noqa
                    holm, jsd_bits, read_jsonl, save_json, setup_logging, shares, wilson)

BAN_CONDS = ["baseline", "placebo", "ban_r1", "ban_r2", "ban_r3", "ban_r4", "ban_top3", "ban_top5", "ban_rare",
             "para1_r1", "para2_r1"]


def load() -> list[dict]:
    orc = {r["id"]: r for r in read_jsonl(ORACLE_PATH)}
    rows = read_jsonl(LABELS_PATH)
    for r in rows:
        o = orc.get(r["id"])
        r["pass"] = None if o is None else bool(o["passed"])
        r["oracle_status"] = None if o is None else o["status"]
        r["shortest_rate"] = None if o is None else o.get("shortest_rate")
    return rows


def offmenu(rs: list[dict], task: str) -> dict:
    n = len(rs)
    corr_off = [r for r in rs if r["pass"] and r["label"] not in MENUS[task] and r["label"] not in NON_IDEAS]
    rare = Counter(r["label"] for r in rs if r["pass"] and r["label"] in RARE_CORRECT[task])
    p = wilson(len(corr_off), n)
    return dict(off_menu_correct=len(corr_off), off_menu_correct_share=p[0], ci=[p[1], p[2]],
                off_menu_correct_by_idea=dict(Counter(r["label"] for r in corr_off)), rare_correct=dict(rare))


def cond_table(rs: list[dict], task: str) -> dict:
    labs = [r["label"] for r in rs]
    n = len(labs)
    h, lo, hi = entropy_ci(labs, 2000, seed=2)
    ps = [r["pass"] for r in rs if r["pass"] is not None]
    pw = wilson(sum(ps), len(ps))
    sb = sum(r["still_banned"] for r in rs)
    sr = [r["shortest_rate"] for r in rs if r["shortest_rate"] is not None and r["oracle_status"] == "pass"]
    return dict(n=n, counts=dict(Counter(labs).most_common()), entropy_bits=h, entropy_ci=[lo, hi],
                still_banned=sb, still_banned_pct=100 * sb / n if n else None, pass_rate=pw[0], pass_ci=[pw[1], pw[2]],
                oracle_status=dict(Counter(r["oracle_status"] for r in rs)),
                mean_shortest_rate_among_pass=float(np.mean(sr)) if sr else None,
                trunc_rate=sum(r["finish_reason"] == "length" for r in rs) / n if n else None, **offmenu(rs, task))


def chi2_pooled(c1: Counter, c2: Counter) -> dict:
    keys = sorted(set(c1) | set(c2))
    n1, n2 = sum(c1.values()), sum(c2.values())
    tab = np.array([[c1.get(k, 0), c2.get(k, 0)] for k in keys], float)
    exp = tab.sum(1, keepdims=True) * np.array([[n1, n2]]) / (n1 + n2)
    keep = (exp >= 5).all(1)
    rest = tab[~keep].sum(0, keepdims=True)
    t2 = np.vstack([tab[keep], rest]) if (~keep).any() else tab[keep]
    t2 = t2[t2.sum(1) > 0]
    if len(t2) < 2:
        return dict(chi2=None, p=None)
    chi, p, dof, _ = stats.chi2_contingency(t2.T)
    return dict(chi2=float(chi), dof=int(dof), p=float(p), classes_kept=[k for k, kk in zip(keys, keep) if kk])


def perm_jsd(a: list[str], b: list[str], n_perm: int = 10000, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    obs = jsd_bits(shares(a), shares(b))
    pool = np.array(a + b)
    na = len(a)
    ge = 0
    for _ in range(n_perm):
        rng.shuffle(pool)
        if jsd_bits(shares(pool[:na].tolist()), shares(pool[na:].tolist())) >= obs - 1e-12:
            ge += 1
    boots = []
    A, B = np.array(a), np.array(b)
    for _ in range(1000):
        boots.append(jsd_bits(shares(A[rng.integers(0, len(A), len(A))].tolist()),
                              shares(B[rng.integers(0, len(B), len(B))].tolist())))
    return dict(jsd=obs, jsd_boot_ci=np.quantile(boots, [.025, .975]).tolist(), perm_p=(ge + 1) / (n_perm + 1))


@logger.catch(reraise=True)
def main() -> None:
    setup_logging("s3_screen")
    rows = load()
    ban = [r for r in rows if r["source"] == "ban"]
    plan = __import__("json").loads((INPUTS / "ban" / "ban_plan.json").read_text())
    out: dict = dict(note_topup="__topup files absent in iteration-1 workspace; noise floor from baseline thirds",
                     tables={}, forced={}, regularity={}, noise_floor={}, candidates={}, wording_P1={},
                     compliance={}, grid_vs_P1={}, menus={})
    csv_rows = []
    for task in ("T1", "T2", "T3"):
        tr = [r for r in ban if r["task"] == task]
        base = [r for r in tr if r["cond"] == "baseline"]
        bc = Counter(r["label"] for r in base)
        menu = sorted([k for k, v in bc.items() if k not in NON_IDEAS and v / len(base) >= 0.03],
                      key=lambda k: -bc[k])
        assert set(menu) == set(MENUS[task]), (task, menu)
        out["menus"][task] = dict(recomputed=menu, asserted_equal=True)
        out["tables"][task] = {}
        for cond in BAN_CONDS:
            rs = [r for r in tr if r["cond"] == cond]
            if not rs:
                continue
            t = cond_table(rs, task)
            t["banned"] = plan[task].get(cond, [])
            t["provenance"] = f"inputs/ban/gen/{task}/{cond}.jsonl (all rows)"
            out["tables"][task][cond] = t
            csv_rows.append(dict(task=task, condition=cond, n=t["n"], entropy_bits=round(t["entropy_bits"], 3),
                                 still_banned_pct=t["still_banned_pct"], pass_rate=round(t["pass_rate"], 3),
                                 off_menu_correct_share=round(t["off_menu_correct_share"], 3),
                                 counts=";".join(f"{k}:{v}" for k, v in t["counts"].items()),
                                 provenance=t["provenance"]))
        # forced purity
        out["forced"][task] = {}
        for cond in sorted({r["cond"] for r in tr if r["cond"].startswith("forced_")}):
            rs = [r for r in tr if r["cond"] == cond]
            cls = cond[len("forced_"):]
            k = sum(r["label"] == cls for r in rs)
            pw = wilson(k, len(rs))
            ps = [r["pass"] for r in rs if r["pass"] is not None]
            pp = wilson(sum(ps), len(ps))
            out["forced"][task][cls] = dict(n=len(rs), purity=pw[0], purity_ci=[pw[1], pw[2]], pass_rate=pp[0],
                                            pass_ci=[pp[1], pp[2]], counts=dict(Counter(r["label"] for r in rs)))
        # regularity test vs placebo
        plac = Counter(r["label"] for r in tr if r["cond"] == "placebo")
        n_pl = sum(plac.values())
        cells = []
        for cond in ["ban_r1", "ban_r2", "ban_r3", "ban_r4", "ban_top3", "ban_top5", "ban_rare"]:
            bcnt = Counter(r["label"] for r in tr if r["cond"] == cond)
            nb = sum(bcnt.values())
            banned = plan[task][cond]
            for j in sorted((set(bcnt) | set(plac)) - set(banned) - NON_IDEAS):
                if bcnt.get(j, 0) + plac.get(j, 0) == 0:
                    continue
                a, c = bcnt.get(j, 0), plac.get(j, 0)
                _, p = stats.fisher_exact([[a, nb - a], [c, n_pl - c]])
                cells.append(dict(ban=cond, banned=banned, idea=j, c_ban=a, n_ban=nb, c_placebo=c, n_placebo=n_pl,
                                  delta=a / nb - c / n_pl, p=float(p), decrease=a / nb < c / n_pl))
        adj = holm([c["p"] for c in cells]) if cells else []
        for c, pa in zip(cells, adj):
            c["p_holm"] = pa
        out["regularity"][task] = cells
        # noise floor: baseline thirds
        thirds = [Counter(r["label"] for r in base if lo <= r["seed"] < lo + 100) for lo in (0, 100, 200)]
        deltas = {}
        for a, b in combinations(range(3), 2):
            for j in set(thirds[a]) | set(thirds[b]):
                deltas.setdefault(j, []).append(abs(thirds[a].get(j, 0) - thirds[b].get(j, 0)) / 100)
        floor_by = {j: max(v) for j, v in deltas.items()}
        allv = [x for v in deltas.values() for x in v]
        floor = max(allv) if allv else 0.0
        out["noise_floor"][task] = dict(source="baseline thirds (seeds 0-99/100-199/200-299)", per_class_max=floor_by,
                                        median=float(np.median(allv)) if allv else None, global_max=floor)
        out["candidates"][task] = [c for c in cells if c["decrease"] and c["p_holm"] < 0.01
                                   and abs(c["delta"]) > floor]
        # wording robustness within P1
        r1 = [r["label"] for r in tr if r["cond"] == "ban_r1"]
        out["wording_P1"][task] = {p: dict(**perm_jsd([r["label"] for r in tr if r["cond"] == p], r1, 2000),
                                           **chi2_pooled(Counter(r["label"] for r in tr if r["cond"] == p),
                                                         Counter(r1)))
                                   for p in ("para1_r1", "para2_r1")}
        out["compliance"][task] = {c: out["tables"][task][c]["still_banned_pct"] for c in ("ban_r1", "ban_top3",
                                                                                          "ban_top5")}
        # grid-vs-P1 wording check
        g = [r["label"] for r in rows if r["source"] == "grid" and r["task"] == task and r["cond"] == "grid"
             and r["T"] == 0.7 and r["topk"] == -1]
        b = [r["label"] for r in base]
        out["grid_vs_P1"][task] = dict(n_grid=len(g), n_p1=len(b), grid_counts=dict(Counter(g)),
                                       p1_counts=dict(Counter(b)), **perm_jsd(g, b, 10000),
                                       **chi2_pooled(Counter(g), Counter(b)))
        logger.info(f"{task}: menu={menu} candidates={len(out['candidates'][task])} "
                    f"grid-vs-P1 JSD={out['grid_vs_P1'][task]['jsd']:.3f} p={out['grid_vs_P1'][task]['perm_p']:.4f}")
    # co-mention
    from classify import parse_list_names
    com = {}
    for task, kind in (("T1", "graph"), ("T2", "sort"), ("T3", "graph")):
        lists = [parse_list_names(r["output_text"], kind) for r in read_jsonl(INPUTS / "ban" / "gen" / task /
                                                                                "comention.jsonl")]
        classes = sorted({c for l_ in lists for c in l_})
        df = Counter(c for l_ in lists for c in set(l_))
        cooc = {a: {b: sum(1 for l_ in lists if a in l_ and b in l_) for b in classes} for a in classes}
        jac = {a: {b: (cooc[a][b] / (df[a] + df[b] - cooc[a][b]) if (df[a] + df[b] - cooc[a][b]) else 0.0)
                   for b in classes} for a in classes}
        mean_rank = {c: float(np.mean([(l_.index(c) + 1) if c in l_ else 11 for l_ in lists])) for c in classes}
        com[task] = dict(n_lists=len(lists), classes=classes, doc_freq=dict(df), cooc_counts=cooc, jaccard=jac,
                         mean_rank=mean_rank)
    save_json(RESULTS / "comention_sim.json", com)
    save_json(RESULTS / "screen_tables.json", out)
    with (RESULTS / "screen_tables.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(csv_rows[0]))
        w.writeheader()
        w.writerows(csv_rows)
    logger.info("wrote results/screen_tables.json/.csv, results/comention_sim.json")


if __name__ == "__main__":
    main()
