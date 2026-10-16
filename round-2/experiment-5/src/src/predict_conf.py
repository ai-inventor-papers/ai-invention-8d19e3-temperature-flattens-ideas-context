#!/usr/bin/env python3
"""STEP 4b / 4d: apply the FROZEN predictors to never-generated confirmation conditions.

  t1t3   : P0_conf = pooled 3 placebo blocks (n=300); prompt states of every confirmation prompt;
           -> results/frozen_predictions.json (+sha256, committed) BEFORE any confirmation ban is generated.
  t4plan : T4 bans from the T4 baseline ranks (ban-arm rules) + 4 random pairs -> data/conf/T4_plan.json
  t4     : T4 centroids (G at the frozen band from T4 baseline+forced windows; P from T4 forced prompt states),
           frozen variant/beta/eps/kappa (pure transfer) -> results/frozen_predictions_T4.json (+sha256)
"""
from __future__ import annotations

import itertools
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit as F  # noqa: E402  (configures loguru)
from loguru import logger  # noqa: E402
from freeze import assert_frozen, sha256_file, write_frozen  # noqa: E402
from protocol import ROOT  # noqa: E402
from protocol_ext import bannable, user_message  # noqa: E402
import predictors as PR  # noqa: E402

RES = ROOT / "results"
CONF = ROOT / "data" / "conf"
PLACEBOS = ["placebo_b1", "placebo_b2", "placebo_b3"]


def conf_labels(task: str, cond: str) -> list[str]:
    return [r["label"] for r in F.load_jsonl(CONF / "labels" / task / f"{cond}.jsonl")]


def pooled_placebo(task: str) -> np.ndarray:
    K = F.classes(task)
    return sum(F.counts_of(conf_labels(task, b), K) for b in PLACEBOS)


def conf_ps(task: str) -> dict:
    out: dict = {}
    for p in sorted((ROOT / "acts").glob(f"prompt_states_conf_*_{task}.npz")):
        z = np.load(p)
        for k in z.files:
            c, part = k.rsplit("__", 1)
            out.setdefault(c, {})[part] = z[k]
    return out


def ctx_from_saved(task: str, frozen: dict, bge) -> dict:
    p = RES / f"centroids_{task}.npz"
    assert sha256_file(p) == frozen["centroid_sha256"][task], f"centroid hash mismatch {task}"
    z = np.load(p)
    cent = dict(cG=z["cG"], cP=z["cP"], cPu=z["cPu"])
    desc = json.loads((ROOT / "src" / "descriptions.json").read_text())
    E_bge, valid_bge = F.bge_class_emb(bge, task, desc)
    S_lex, valid_lex = F.qwen_name_S(task)
    return dict(cent=cent, band=frozen["band"], massive=frozen["massive_dims"], norms=frozen["norms"], S_G=z["S_G"],
                E_bge=E_bge, valid_bge=valid_bge, S_bge=E_bge @ E_bge.T, S_lex=S_lex, valid_lex=valid_lex,
                S_beh=z["S_beh"], q=z["q"], bge=bge)


def predict_all(item: dict, frozen: dict) -> dict:
    params = {"A": 0.0, "B": frozen["beta"], "C": frozen["lambda_nested"], "D": frozen["beta_D"],
              "D2": frozen["beta_D2"], "D3": frozen["beta_D3"], "E": frozen["beta_E"]}
    it = dict(item)
    it["s"] = dict(item["s"], B=item["s"][f"B:{frozen['variant']}"])
    if not it["B"]:  # no banned idea (mention / alt placebo / cross-domain): similarity terms have no anchor
        for k in ("D", "D3", "E"):
            it["s"][k] = np.zeros_like(it["s"]["B"])
    return {k: PR.predict(k, it, frozen["eps"], frozen["kappa"], p).tolist() for k, p in params.items()}


def conditions_for(task: str) -> list[tuple[str, list[str]]]:
    jobs = json.loads((CONF / "jobs_conf_bans.json").read_text()) + json.loads((CONF / "jobs_conf_nonban.json").read_text())
    out = []
    for j in jobs:
        if j["task"] != task or j["condition"] in PLACEBOS or j["condition"] in ("baseline", "comention") \
                or j["condition"].startswith("forced_"):
            continue
        out.append((j["condition"], j["banned"]))
    return out


def run_t1t3() -> None:
    frozen_p = RES / "frozen_predictors.json"
    assert_frozen(frozen_p)
    frozen = json.loads(frozen_p.read_text())
    bge = F.bge_model()
    out: dict = {"frozen_predictors_sha256": sha256_file(frozen_p), "tasks": {}}
    for t in ("T1", "T2", "T3"):
        ctx = ctx_from_saved(t, frozen, bge)
        ps = conf_ps(t)
        sps = F.prompt_states(t)
        c0 = pooled_placebo(t)
        c0_screen = F.counts_of(F.screen_labels(t, "placebo"), F.classes(t))
        pl_msg = user_message(t, "placebo")
        tout = {"classes": F.classes(t), "P0_conf_counts": c0.tolist(), "P0_screen_counts": c0_screen.tolist(),
                "conditions": {}}
        # placebo-state agreement: conf placebo prompt state must equal the screen placebo state (same text)
        tout["placebo_state_maxabs_conf_vs_screen"] = float(np.abs(ps["placebo_b1"]["suf"] - sps["placebo"]["suf"]).max())
        for cond, banned in conditions_for(t):
            um = user_message(t, cond, banned)
            item = F.make_item(t, cond, banned, np.zeros(len(F.classes(t))), c0, ctx, ps, "placebo_b1", um, pl_msg)
            pred = predict_all(item, frozen)
            item_s = F.make_item(t, cond, banned, np.zeros(len(F.classes(t))), c0_screen, ctx, ps, "placebo_b1", um, pl_msg)
            pred["B_screenP0"] = predict_all(item_s, frozen)["B"]
            tout["conditions"][cond] = dict(banned=banned, user_message=um, pred=pred,
                                            s_B=item["s"][f"B:{frozen['variant']}"].tolist(),
                                            delta_norm=float(np.linalg.norm(F.delta(ps, cond, "placebo_b1", frozen["band"],
                                                                                     frozen["variant"]))))
        out["tasks"][t] = tout
        logger.info(f"{t}: frozen predictions for {len(tout['conditions'])} conditions")
    h = write_frozen(RES / "frozen_predictions.json", out, "FREEZE per-condition predictions before confirmation bans")
    logger.info(f"FROZEN predictions sha256={h}")


def run_t4plan() -> None:
    K = F.classes("T4")
    labs = conf_labels("T4", "baseline")
    cnt = Counter(labs)
    com_lists = F.comention_S("T4")[1]
    com = Counter(c for lst in com_lists for c in set(lst))
    bann = bannable("T4")
    ranked = sorted(bann, key=lambda c: (-cnt.get(c, 0), -com.get(c, 0), bann.index(c)))
    nonzero = [c for c in ranked if cnt.get(c, 0) >= 1]
    filled = [c for c in ranked if cnt.get(c, 0) == 0][: max(0, 5 - len(nonzero))]
    top = (nonzero + filled)[:5]
    N = sum(v for k, v in cnt.items() if k != "Unparseable")
    rates = {c: cnt.get(c, 0) / N for c in bann}
    in_band = [c for c in bann if 0.01 <= rates[c] <= 0.05 and c not in top[:4]]
    if in_band:
        rare, rule = min(in_band, key=lambda c: abs(rates[c] - 0.03)), "in [1%,5%], closest to 3%"
    else:
        nz = [c for c in bann if rates[c] > 0 and c not in top[:4]]
        if nz:
            rare, rule = min(nz, key=lambda c: abs(rates[c] - 0.03)), "no class in [1%,5%]: nonzero closest to 3% (excluding ranks 1-4)"
        else:
            zero = [c for c in ranked if c not in top]
            rare = max(zero, key=lambda c: com.get(c, 0)) if zero else top[-1]
            rule = "no nonzero class outside ranks 1-4: most co-mentioned zero-rate class"
    conds = {"ban_r1": [top[0]], "ban_r2": [top[1]], "ban_r3": [top[2]], "ban_r4": [top[3]], "ban_top3": top[:3],
             "ban_top5": top[:5], "ban_rare": [rare]}
    seen = {c for c in bann if cnt.get(c, 0) >= 1}
    for t in ("forced_" + c for c in bann):
        p = CONF / "labels" / "T4" / f"{t}.jsonl"
        if p.exists():
            seen |= {r["label"] for r in F.load_jsonl(p) if r["label"] in bann}
    cls = [c for c in bann if c in seen]
    screen_sets = {frozenset(v) for v in conds.values()}
    combos = [list(c) for c in itertools.combinations(cls, 2) if frozenset(c) not in screen_sets]
    rng = np.random.default_rng(20261017)
    pick = rng.choice(len(combos), size=min(4, len(combos)), replace=False)
    for i in pick:
        a, b = sorted(combos[i], key=K.index)
        conds[f"pair_{a}__{b}"] = [a, b]
    plan = dict(counts=dict(cnt), comention_doc_freq=dict(com), ranked=ranked, top5=top, filled_by_comention=filled,
                rare=rare, rare_rule=rule, n_classes_ge3pct=sum(r >= 0.03 for r in rates.values()), conditions=conds)
    (CONF / "T4_plan.json").write_text(json.dumps(plan, indent=1))
    logger.info(f"T4 plan: counts={dict(cnt.most_common())} top5={top} rare={rare} ({rule}) conds={list(conds)}")


def run_t4() -> None:
    frozen_p = RES / "frozen_predictors.json"
    assert_frozen(frozen_p)
    frozen = json.loads(frozen_p.read_text())
    band = frozen["band"]
    bge = F.bge_model()
    K = F.classes("T4")
    # G centroids from T4 baseline + forced windows (band layers only were computed)
    zb = np.load(ROOT / "acts" / "gen_conf" / "T4" / "baseline.npz")
    layers = [int(x) for x in zb["layers"]]
    assert layers == band, (layers, band)
    yb = conf_labels("T4", "baseline")
    Xs, ys = [zb["window"].astype(np.float32).mean(1)], list(yb)
    for c in bannable("T4"):
        p = ROOT / "acts" / "gen_conf" / "T4" / f"forced_{c}.npz"
        z = np.load(p)
        Xs.append(z["window"].astype(np.float32).mean(1))
        ys += conf_labels("T4", f"forced_{c}")
    X = np.concatenate(Xs)
    y = np.array(ys)
    mu = X.mean(0)
    d = X.shape[1]
    cG = np.full((len(K), d), np.nan)
    nG = {}
    for j, c in enumerate(K):
        if c == "Unparseable":
            continue
        m = y == c
        nG[c] = int(m.sum())
        if m.sum() >= F.MIN_N:
            cG[j] = X[m].mean(0) - mu
    ps = conf_ps("T4")
    bidx = [l - 1 for l in band]
    fs = {c: ps[f"forced_{c}"]["suf"][bidx].mean(0).mean(0) for c in bannable("T4")}
    fu = {c: ps[f"forced_{c}"]["umean"][bidx].mean(0) for c in bannable("T4")}
    cP = np.full((len(K), d), np.nan)
    cPu = np.full((len(K), d), np.nan)
    ms, mu_ = np.mean(list(fs.values()), 0), np.mean(list(fu.values()), 0)
    for j, c in enumerate(K):
        if c in fs:
            cP[j], cPu[j] = fs[c] - ms, fu[c] - mu_
    import geometry as GEO
    S_G = GEO.cos_matrix(cG)
    S_beh, lists = F.comention_S("T4")
    q = F.q_share("T4", lists)
    desc = json.loads((ROOT / "src" / "descriptions.json").read_text())
    E_bge, valid_bge = F.bge_class_emb(bge, "T4", desc)
    S_lex, valid_lex = F.qwen_name_S("T4")
    np.savez(RES / "centroids_T4.npz", classes=np.array(K), cG=cG, cP=cP, cPu=cPu, mu=mu, S_G=S_G, S_bge=E_bge @ E_bge.T,
             S_lex=S_lex, S_beh=S_beh, q=q, band=np.array(band))
    ctx = dict(cent=dict(cG=cG, cP=cP, cPu=cPu), band=band, massive=frozen["massive_dims"], norms=frozen["norms"],
               S_G=S_G, E_bge=E_bge, valid_bge=valid_bge, S_bge=E_bge @ E_bge.T, S_lex=S_lex, valid_lex=valid_lex,
               S_beh=S_beh, q=q, bge=bge)
    plan = json.loads((CONF / "T4_plan.json").read_text())
    c0 = pooled_placebo("T4")
    pl_msg = user_message("T4", "placebo")
    out = {"frozen_predictors_sha256": sha256_file(frozen_p), "centroids_T4_sha256": sha256_file(RES / "centroids_T4.npz"),
           "classes": K, "nG": nG, "P0_conf_counts": c0.tolist(), "conditions": {}}
    for cond, banned in plan["conditions"].items():
        um = user_message("T4", cond, banned)
        item = F.make_item("T4", cond, banned, np.zeros(len(K)), c0, ctx, ps, "placebo_b1", um, pl_msg)
        out["conditions"][cond] = dict(banned=banned, user_message=um, pred=predict_all(item, frozen),
                                       s_B=item["s"][f"B:{frozen['variant']}"].tolist())
    h = write_frozen(RES / "frozen_predictions_T4.json", out, "FREEZE T4 predictions (pure transfer) before T4 bans")
    logger.info(f"FROZEN T4 predictions sha256={h}; nG={nG}")


if __name__ == "__main__":
    {"t1t3": run_t1t3, "t4plan": run_t4plan, "t4": run_t4}[sys.argv[1]]()
