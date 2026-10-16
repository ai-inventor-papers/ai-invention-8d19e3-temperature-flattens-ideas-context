#!/usr/bin/env python3
"""Post-hoc analyses (CPU): transplant recovery (C2c), edge-vs-far-side statistic, logit lens of Delta_h,
manifold (PCA/UMAP) with placebo->ban arrows and prompt-displacement arrows, and all figures.

Usage: python src/analysis.py transplant | edge | lens | manifold | figures | all
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit as F  # noqa: E402
from loguru import logger  # noqa: E402
from protocol import MODEL, ROOT  # noqa: E402
from protocol_ext import DISPLAY_ALL  # noqa: E402
import predictors as PR  # noqa: E402

RES = ROOT / "results"
FIG = ROOT / "figures"
TR = ROOT / "data" / "transplant"
NB = 2000
PRE_BANS = [("T1", "ban_r1"), ("T1", "ban_r4"), ("T1", "ban_top3"), ("T2", "ban_rare"), ("T2", "ban_top5"),
            ("T3", "ban_r1")]


def frozen() -> dict:
    return json.loads((RES / "frozen_predictors.json").read_text())


# ============================================================================================ transplant
def transplant_labels() -> dict:
    """Label every transplant cell (v1 + oracle); cached per cell in data/transplant_labels."""
    from label_conf import label_records
    out = {}
    for p in sorted(TR.glob("*/*/*.jsonl")):
        t, b, c = p.parts[-3], p.parts[-2], p.stem
        lp = ROOT / "data" / "transplant_labels" / t / b / f"{c}.jsonl"
        recs = F.load_jsonl(p)
        if lp.exists() and len(F.load_jsonl(lp)) == len(recs):
            rows = F.load_jsonl(lp)
        else:
            rows = label_records(recs, t, run_oracle=True, workers=24)
            for r, rec in zip(rows, recs):
                r["hit_max"] = rec.get("hit_max")
            lp.parent.mkdir(parents=True, exist_ok=True)
            lp.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
            logger.info(f"labelled {t}/{b}/{c}: {dict(Counter(x['label'] for x in rows).most_common())}")
        out[(t, b, c)] = rows
    return out


def dist(labels: list[str], K: list[str]) -> np.ndarray:
    c = F.counts_of(labels, K)
    return c / max(c.sum(), 1)


def recovery(cell: list[str], ref_ban: list[str], ref_pl: list[str], K: list[str]) -> float:
    den = PR.jsd(dist(ref_pl, K), dist(ref_ban, K))
    return 1 - PR.jsd(dist(cell, K), dist(ref_ban, K)) / den if den > 0 else float("nan")


def restoration(cell: list[str], ref_ban: list[str], ref_pl: list[str], K: list[str]) -> float:
    den = PR.jsd(dist(ref_ban, K), dist(ref_pl, K))
    return 1 - PR.jsd(dist(cell, K), dist(ref_pl, K)) / den if den > 0 else float("nan")


def boot(fn, arrays: list[list[str]], seed: int = 0, n: int = NB) -> list[float]:
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        res = [[a[i] for i in rng.integers(0, len(a), len(a))] for a in arrays]
        out.append(fn(*res))
    return out


def ci(v: list[float]) -> list[float]:
    v = [x for x in v if np.isfinite(x)]
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] if v else [None, None]


def run_transplant() -> dict:
    labs = transplant_labels()
    lab = {k: [r["label"] for r in v] for k, v in labs.items()}
    out: dict = {"bans": {}, "cells_n": {f"{k[0]}/{k[1]}/{k[2]}": len(v) for k, v in lab.items()}}
    for t, b in PRE_BANS:
        K = F.classes(t)
        pl = lab.get((t, "placebo", "REF_placebo"))
        rb = lab.get((t, b, "REF_ban"))
        if pl is None or rb is None:
            continue
        e: dict = {"jsd_refplacebo_refban": PR.jsd(dist(pl, K), dist(rb, K)),
                   "dist": {"REF_placebo": dict(Counter(pl)), "REF_ban": dict(Counter(rb))}}
        for c in ("TRANSPLANT", "OFFTARGET", "SUFFIX_CEILING", "ALLPOS", "TRANSPLANT_L8", "TRANSPLANT_L18"):
            x = lab.get((t, b, c))
            if x is None:
                continue
            fn = lambda cc, rbb, pll: recovery(cc, rbb, pll, K)  # noqa: E731
            e[c] = dict(R=recovery(x, rb, pl, K), ci95=ci(boot(fn, [x, rb, pl])), n=len(x))
            e["dist"][c] = dict(Counter(x))
        x = lab.get((t, b, "RESTORE"))
        if x is not None:
            fn = lambda cc, rbb, pll: restoration(cc, rbb, pll, K)  # noqa: E731
            e["RESTORE"] = dict(restoration=restoration(x, rb, pl, K), ci95=ci(boot(fn, [x, rb, pl])), n=len(x))
            e["dist"]["RESTORE"] = dict(Counter(x))
        for c in ("KNOCKOUT_BAN", "KNOCKOUT_PLACEBO_SENT"):  # decode-time attention knockout of the sentence
            x = lab.get((t, b, c))
            if x is None:
                continue
            fn = lambda cc, rbb, pll: restoration(cc, rbb, pll, K)  # noqa: E731
            e[c] = dict(restoration=restoration(x, rb, pl, K), ci95=ci(boot(fn, [x, rb, pl])),
                        jsd_to_ref_placebo=PR.jsd(dist(x, K), dist(pl, K)), jsd_to_ref_ban=PR.jsd(dist(x, K), dist(rb, K)),
                        n=len(x))
            e["dist"][c] = dict(Counter(x))
        draws = [lab.get((t, b, f"RAND_{i}")) for i in range(1, 6)]
        draws = [d for d in draws if d is not None]
        if draws:
            per = [recovery(d, rb, pl, K) for d in draws]
            rng = np.random.default_rng(1)
            bs = []
            for _ in range(NB):
                di = rng.integers(0, len(draws), len(draws))
                rb_ = [rb[i] for i in rng.integers(0, len(rb), len(rb))]
                pl_ = [pl[i] for i in rng.integers(0, len(pl), len(pl))]
                vals = []
                for k in di:
                    d = draws[k]
                    vals.append(recovery([d[i] for i in rng.integers(0, len(d), len(d))], rb_, pl_, K))
                bs.append(float(np.nanmean(vals)))
            e["RAND"] = dict(R_mean=float(np.mean(per)), per_draw=per, ci95=ci(bs), n_draws=len(draws))
            for i, d in enumerate(draws, 1):
                e["dist"][f"RAND_{i}"] = dict(Counter(d))
        # C4 inputs: oracle pass rate and correct counts per idea
        c4 = {}
        for c in ("REF_ban", "TRANSPLANT", "RESTORE"):
            rows = labs.get((t, b, c))
            if rows:
                c4[c] = dict(pass_rate=float(np.mean([r.get("oracle_pass", False) for r in rows])),
                             correct_by_idea=dict(Counter(r["label"] for r in rows if r.get("oracle_pass"))))
        rows = labs.get((t, "placebo", "REF_placebo"))
        c4["REF_placebo"] = dict(pass_rate=float(np.mean([r.get("oracle_pass", False) for r in rows])),
                                 correct_by_idea=dict(Counter(r["label"] for r in rows if r.get("oracle_pass"))))
        e["c4"] = c4
        out["bans"][f"{t}/{b}"] = e
    bans = list(out["bans"].values())
    Rt = [x["TRANSPLANT"]["R"] for x in bans if "TRANSPLANT" in x]
    Rr = [x["RAND"]["R_mean"] for x in bans if "RAND" in x]
    beats = sum(x["TRANSPLANT"]["R"] > x["OFFTARGET"]["R"] for x in bans if "TRANSPLANT" in x and "OFFTARGET" in x)
    out["summary"] = dict(mean_R_transplant=float(np.mean(Rt)) if Rt else None,
                          mean_R_random=float(np.mean(Rr)) if Rr else None,
                          transplant_beats_offtarget=f"{beats}/{len(bans)}",
                          mean_restoration=float(np.mean([x["RESTORE"]["restoration"] for x in bans if "RESTORE" in x]))
                          if bans else None)
    kb = [x["KNOCKOUT_BAN"]["restoration"] for x in bans if "KNOCKOUT_BAN" in x]
    out["summary"]["mean_restoration_knockout_ban_sentence"] = float(np.mean(kb)) if kb else None
    s = out["summary"]
    out["c2c_pass"] = bool(Rt and Rr and s["mean_R_transplant"] >= 0.5 and s["mean_R_random"] <= 0.15 and beats >= 4)
    (RES / "transplant.json").write_text(json.dumps(out, indent=1))
    logger.info(f"transplant summary: {s} pass={out['c2c_pass']}")
    return out


# ============================================================================================ edge statistic
def edge_stat() -> dict:
    """E_b = sum_{j unbanned} (P_obs_u(j) - P_IIA_u(j)) * Sbar_jB over unbanned-conditional distributions."""
    fz = frozen()
    eps = fz["eps"]
    out: dict = {"screen": {}, "conf": {}}
    rng = np.random.default_rng(0)
    plan = json.loads((ROOT / "data" / "ban_plan.json").read_text())

    def one(K, counts, counts0, q, banned, S, valid):
        B = [K.index(c) for c in banned]
        if not all(valid[b] for b in B):
            return None
        unb = np.array([valid[j] and j not in B for j in range(len(K))])
        if unb.sum() < 2:
            return None
        Pt0 = PR.floor_P0(counts0, q, eps)
        piia = Pt0 * unb
        piia = piia / piia.sum()

        def E(cnt, Sm):
            po = cnt * unb
            if po.sum() == 0:
                return np.nan
            po = po / po.sum()
            sbar = np.nanmean(Sm[:, B], axis=1)
            return float(np.nansum((po - piia)[unb] * sbar[unb]))
        e = E(counts, S)
        vidx = np.where(valid)[0]
        null = []
        for _ in range(1000):
            perm = vidx.copy()
            rng.shuffle(perm)
            Sp = S.copy()
            Sp[np.ix_(vidx, vidx)] = S[np.ix_(perm, perm)]
            null.append(E(counts, Sp))
        labs_idx = np.repeat(np.arange(len(K)), counts.astype(int))
        bs = []
        for _ in range(1000):
            smp = rng.choice(labs_idx, len(labs_idx))
            bs.append(E(np.bincount(smp, minlength=len(K)).astype(float), S))
        null = np.array(null)
        return dict(E=e, ci95=ci(bs), null_mean=float(np.nanmean(null)), p_two_sided=float(np.mean(np.abs(null - np.nanmean(null)) >= abs(e - np.nanmean(null)))),
                    direction="edge (attraction to banned neighbours)" if e > 0 else "far side / family suppression")
    for t in ("T1", "T2", "T3"):
        z = np.load(RES / f"centroids_{t}.npz")
        K = list(z["classes"])
        SG, Sbge = z["S_G"], z["S_bge"]
        validG = ~np.isnan(z["cG"][:, 0])
        validB = np.array([c in DISPLAY_ALL for c in K])
        c0 = F.counts_of(F.screen_labels(t, "placebo"), K)
        for c in F.SCREEN_BANS:
            cnt = F.counts_of(F.screen_labels(t, c), K)
            out["screen"][f"{t}/{c}"] = dict(banned=plan[t][c], internal=one(K, cnt, c0, z["q"], plan[t][c], SG, validG),
                                             external_bge=one(K, cnt, c0, z["q"], plan[t][c], Sbge, validB))
    fp = json.loads((RES / "frozen_predictions.json").read_text())
    tasks = dict(fp["tasks"])
    if (RES / "frozen_predictions_T4.json").exists():
        f4 = json.loads((RES / "frozen_predictions_T4.json").read_text())
        tasks["T4"] = dict(classes=f4["classes"], P0_conf_counts=f4["P0_conf_counts"], conditions=f4["conditions"])
    for t, td in tasks.items():
        z = np.load(RES / f"centroids_{t}.npz")
        K = list(z["classes"])
        validG = ~np.isnan(z["cG"][:, 0])
        validB = np.array([c in DISPLAY_ALL for c in K])
        c0 = np.array(td["P0_conf_counts"], float)
        for cond, cd in td["conditions"].items():
            p = ROOT / "data" / "conf" / "labels" / t / f"{cond}.jsonl"
            if not cd["banned"] or not p.exists():
                continue
            cnt = F.counts_of([r["label"] for r in F.load_jsonl(p)], K)
            out["conf"][f"{t}/{cond}"] = dict(banned=cd["banned"],
                                              internal=one(K, cnt, c0, z["q"], cd["banned"], z["S_G"], validG),
                                              external_bge=one(K, cnt, c0, z["q"], cd["banned"], z["S_bge"], validB))
    summ = {}
    for t in ("T1", "T2", "T3"):
        e = out["screen"].get(f"{t}/ban_top5", {}).get("internal")
        summ[f"{t}/ban_top5"] = e
    out["top5_summary"] = summ
    allE = [v["internal"]["E"] for v in list(out["screen"].values()) + list(out["conf"].values())
            if v["internal"] and np.isfinite(v["internal"]["E"])]
    out["overall"] = dict(n=len(allE), n_positive=int(sum(e > 0 for e in allE)), mean=float(np.mean(allE)) if allE else None)
    (RES / "edge_stat.json").write_text(json.dumps(out, indent=1))
    logger.info(f"edge stat overall: {out['overall']}; top5: { {k: (v or {}).get('E') for k, v in summ.items()} }")
    return out


# ============================================================================================ logit lens
def logit_lens() -> dict:
    from huggingface_hub import snapshot_download
    from safetensors import safe_open
    from transformers import AutoTokenizer
    fz = frozen()
    band = fz["band"]
    tok = AutoTokenizer.from_pretrained(MODEL)
    path = Path(snapshot_download(MODEL, allow_patterns=["*.safetensors", "*.json"]))
    W = g = None
    for f in sorted(path.glob("*.safetensors")):
        with safe_open(str(f), framework="pt") as fh:
            ks = fh.keys()
            if "model.embed_tokens.weight" in ks:
                W = fh.get_tensor("model.embed_tokens.weight").float().numpy()
            if "model.norm.weight" in ks:
                g = fh.get_tensor("model.norm.weight").float().numpy()
    plan = json.loads((ROOT / "data" / "ban_plan.json").read_text())

    def name_ids(c: str) -> set[int]:
        ids = set()
        for s in {DISPLAY_ALL[c], DISPLAY_ALL[c].split(" (")[0], c.replace("_", " "), c.split("_")[0]}:
            for v in (s, " " + s, s.capitalize(), " " + s.capitalize()):
                t = tok(v, add_special_tokens=False)["input_ids"]
                if t:
                    ids.add(t[0])
        m = re.search(r"\((\w+)\)", DISPLAY_ALL[c])
        if m:
            for v in (m.group(1), " " + m.group(1)):
                ids.add(tok(v, add_special_tokens=False)["input_ids"][0])
        return ids
    out = {}
    for t in ("T1", "T2", "T3"):
        ps = F.prompt_states(t)
        for c in F.SCREEN_BANS:
            res = {}
            for name, layers in (("band", band), ("L35", [35])):
                d = np.mean([ps[c]["suf"][l - 1] - ps["placebo"]["suf"][l - 1] for l in layers], 0).mean(0)
                h = d / np.sqrt(np.mean(d ** 2) + 1e-6) * g
                logits = W @ h
                order = np.argsort(-logits)
                rank = np.empty_like(order)
                rank[order] = np.arange(len(order))
                top = [tok.decode([i]) for i in order[:20]]
                ranks = {b: int(min(rank[i] for i in name_ids(b))) for b in plan[t][c]}
                res[name] = dict(top20=top, banned_name_rank=ranks)
            out[f"{t}/{c}"] = res
    (RES / "logit_lens.json").write_text(json.dumps(out, indent=1))
    med = np.median([min(v["band"]["banned_name_rank"].values()) for v in out.values()])
    logger.info(f"logit lens: median best banned-name rank at band = {med}")
    return out


# ============================================================================================ manifold
def text_features(rec: dict) -> dict:
    txt = rec["output_text"]
    fence = txt.find("```")
    return dict(n_out_tokens=len(rec.get("output_token_ids") or []), truncated=float(rec.get("finish_reason") == "length"),
                n_headers=len(re.findall(r"(?m)^#{1,6}\s", txt)), prose_before_code=fence if fence >= 0 else len(txt),
                has_main_guard=float("__main__" in txt))


def manifold() -> dict:
    from sklearn.decomposition import PCA
    fz = frozen()
    band = fz["band"]
    out = {}
    for t in ("T1", "T2", "T3", "T4"):
        gen_dir = "gen" if t != "T4" else "gen_conf"
        try:
            Xb, yb = F.baseline_set(t, gen_dir)
            Xf, yf, _ = F.forced_set(t, gen_dir)
        except (FileNotFoundError, AssertionError) as e:
            logger.warning(f"manifold {t}: {e}")
            continue
        layers = list(range(1, 36)) if t != "T4" else band
        Gb, Gf = F.band_mean_window(Xb, band, layers), F.band_mean_window(Xf, band, layers)
        X = np.concatenate([Gb, Gf])
        y = np.array(yb + yf)
        pca = PCA(n_components=10, random_state=0).fit(X)
        Z = pca.transform(X)
        K = F.classes(t)
        res: dict = {"explained_var": pca.explained_variance_ratio_.tolist(), "conditions": {}, "samples": {}}
        # eta^2 of label on PC1..3
        eta = []
        for k in range(3):
            v = Z[:, k]
            ss_t = ((v - v.mean()) ** 2).sum()
            ss_b = sum((v[y == c].mean() - v.mean()) ** 2 * (y == c).sum() for c in set(y))
            eta.append(float(ss_b / ss_t))
        res["eta2_label_pc"] = eta
        if eta[0] < 0.3:  # pre-declared: supervised 2-D display when PC1 is not label-dominated
            from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
            keep = np.isin(y, [c for c, n in Counter(y).items() if n >= 2])
            lda = LinearDiscriminantAnalysis(n_components=2).fit(X[keep], y[keep])
            res["lda"] = dict(coords=lda.transform(X)[:, :2].round(3).tolist(), label=y.tolist(),
                              note="supervised display only")
        # PC1 vs surface features (baseline samples)
        brecs = F.load_jsonl((ROOT / "data" / ("gen" if t != "T4" else "conf/gen") / t / "baseline.jsonl"))
        feats = [text_features(r) for r in brecs]
        r2 = {}
        for k in feats[0]:
            xv = np.array([f[k] for f in feats], float)
            if xv.std() > 0:
                r2[k] = float(np.corrcoef(xv, Z[: len(brecs), 0])[0, 1] ** 2)
        res["pc1_r2_surface"] = r2
        res["samples"] = dict(pc=Z[:, :3].round(3).tolist(), label=y.tolist(),
                              source=["baseline"] * len(yb) + ["forced"] * len(yf))
        cent = {}
        for c in sorted(set(y)):
            m = y == c
            cent[c] = dict(zip(("pc1", "pc2", "pc3"), Z[m, :3].mean(0).round(4).tolist()))
            cent[c]["count_baseline"] = int((np.array(yb) == c).sum())
            cent[c]["n_all"] = int(m.sum())
        res["centroids"] = cent
        # conditions: screen (T1-T3) and confirmation windows
        cond_files = []
        if t != "T4":
            cond_files += [(c, ROOT / "acts" / "gen" / t / f"{c}.npz", ROOT / "data" / "labels" / t / f"{c}.jsonl")
                           for c in F.SCREEN_BANS + ["placebo", "baseline"]]
        for p in sorted((ROOT / "acts" / "gen_conf" / t).glob("*.npz")):
            if p.stem.startswith("forced_") or p.stem == "baseline" and t != "T4":
                continue
            cond_files.append(("conf:" + p.stem, p, ROOT / "data" / "conf" / "labels" / t / f"{p.stem}.jsonl"))
        ps_s = F.prompt_states(t) if t != "T4" else {}
        from predict_conf import conf_ps
        ps_c = conf_ps(t)
        pl_ref = ps_s.get("placebo") if t != "T4" else ps_c.get("placebo_b1")
        bidx = [l - 1 for l in band]
        for name, ap, lp in cond_files:
            if not ap.exists() or not lp.exists():
                continue
            z = np.load(ap)
            lay = [int(x) for x in z["layers"]] if "layers" in z.files else list(range(1, 36))
            W = F.band_mean_window(z["window"], band, lay)
            labs = [r["label"] for r in F.load_jsonl(lp)]
            Zc = pca.transform(W)
            per = {}
            for c in sorted(set(labs)):
                m = np.array(labs) == c
                per[c] = dict(zip(("pc1", "pc2", "pc3"), Zc[m, :3].mean(0).round(4).tolist()), count=int(m.sum()))
            entry = dict(ideas=per, mean_point=dict(zip(("pc1", "pc2", "pc3"), Zc[:, :3].mean(0).round(4).tolist())))
            key = name.split(":")[-1]
            src = ps_c if name.startswith("conf:") else ps_s
            if key in src and pl_ref is not None:
                d = (src[key]["suf"][bidx].mean(0) - pl_ref["suf"][bidx].mean(0)).mean(0)
                d[fz["massive_dims"]] = 0
                pd_ = pca.components_[:3] @ d  # projection of the prompt displacement on the PCs (no centering)
                entry["prompt_disp"] = dict(zip(("pc1", "pc2", "pc3"), pd_.round(4).tolist()))
                entry["prompt_disp_norm"] = float(np.linalg.norm(d))
            res["conditions"][name] = entry
        out[t] = res
        logger.info(f"manifold {t}: EV={np.round(pca.explained_variance_ratio_[:3], 3)} eta2={np.round(eta, 3)}")
    (RES / "manifold_coords.json").write_text(json.dumps(out))
    return out


# ============================================================================================ figures
def figures() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"pdf.fonttype": 42, "font.size": 9})
    FIG.mkdir(exist_ok=True)
    cmap = plt.get_cmap("tab20")
    man = json.loads((RES / "manifold_coords.json").read_text()) if (RES / "manifold_coords.json").exists() else {}
    for t, res in man.items():
        smp = res["samples"]
        ideas = sorted(res["centroids"])
        col = {c: cmap(i % 20) for i, c in enumerate(ideas)}
        P = np.array(smp["pc"])
        fig, ax = plt.subplots(figsize=(7, 6))
        for c in ideas:
            m = np.array(smp["label"]) == c
            ax.scatter(P[m, 0], P[m, 1], s=5, color=col[c], alpha=0.25)
        for c, v in res["centroids"].items():
            ax.scatter(v["pc1"], v["pc2"], s=30 + 6 * v["count_baseline"], color=col[c], edgecolor="k", zorder=3)
            ax.annotate(f"{c} ({v['count_baseline']})", (v["pc1"], v["pc2"]), fontsize=7, zorder=4)
        pl = res["conditions"].get("placebo") or res["conditions"].get("conf:placebo_b1")
        top = res["conditions"].get("ban_top5") or res["conditions"].get("conf:ban_top5")
        if pl and top:
            a, b = pl["mean_point"], top["mean_point"]
            ax.annotate("", xy=(b["pc1"], b["pc2"]), xytext=(a["pc1"], a["pc2"]),
                        arrowprops=dict(arrowstyle="->", color="red", lw=2), zorder=5)
            ax.text(b["pc1"], b["pc2"], "top-5 ban (gen mean)", color="red", fontsize=7)
            if "prompt_disp" in top:
                pd_ = np.array([top["prompt_disp"]["pc1"], top["prompt_disp"]["pc2"]])
                span = np.ptp(P[:, :2], axis=0).mean()
                sc = 0.25 * span / max(np.linalg.norm(pd_), 1e-9)
                ax.annotate("", xy=(a["pc1"] + sc * pd_[0], a["pc2"] + sc * pd_[1]), xytext=(a["pc1"], a["pc2"]),
                            arrowprops=dict(arrowstyle="->", color="purple", lw=1.5, ls="--"), zorder=5)
                ax.text(a["pc1"] + sc * pd_[0], a["pc2"] + sc * pd_[1], "prompt Δh (rescaled)", color="purple", fontsize=7)
        if "lda" in res:
            L = np.array(res["lda"]["coords"])
            fig2, ax2 = plt.subplots(figsize=(6, 5))
            for c in ideas:
                m = np.array(res["lda"]["label"]) == c
                ax2.scatter(L[m, 0], L[m, 1], s=6, color=col[c], alpha=0.5, label=c)
            ax2.legend(fontsize=6, markerscale=3)
            ax2.set_title(f"{t}: LDA(label) 2-D view - supervised display only")
            fig2.tight_layout()
            for ext in ("png", "pdf"):
                fig2.savefig(FIG / f"manifold_{t}_lda.{ext}", dpi=150)
            plt.close(fig2)
        ev = res["explained_var"]
        ax.set_xlabel(f"PC1 ({ev[0]:.1%})")
        ax.set_ylabel(f"PC2 ({ev[1]:.1%})")
        ax.set_title(f"{t}: generated-window idea manifold (band layers), discs sized by baseline count")
        fig.tight_layout()
        for ext in ("png", "pdf"):
            fig.savefig(FIG / f"manifold_{t}_pca.{ext}", dpi=150)
        plt.close(fig)
        # UMAP secondary
        try:
            import umap
            U = umap.UMAP(n_neighbors=30, min_dist=0.3, random_state=0).fit_transform(np.array(smp["pc"]))
            fig, ax = plt.subplots(figsize=(6, 5))
            for c in ideas:
                m = np.array(smp["label"]) == c
                ax.scatter(U[m, 0], U[m, 1], s=5, color=col[c], alpha=0.5, label=c)
            ax.legend(fontsize=6, markerscale=3)
            ax.set_title(f"{t}: UMAP of PCs 1-3 (secondary display)")
            fig.tight_layout()
            for ext in ("png", "pdf"):
                fig.savefig(FIG / f"manifold_{t}_umap.{ext}", dpi=150)
            plt.close(fig)
        except Exception as e:  # noqa: BLE001 - UMAP is a secondary display only
            logger.warning(f"umap {t}: {e}")
    # predictor JSD bars
    sc = RES / "predictor_scores_screen.json"
    cc = RES / "predictor_scores_conf.json"
    if sc.exists() and cc.exists():
        s = json.loads(sc.read_text())
        c = json.loads(cc.read_text())
        preds = PR.PREDICTORS
        names = {"A": "IIA", "B": "Δh-disp", "C": "nested", "D": "bge", "D2": "bge-prompt", "D3": "lexical", "E": "co-mention"}
        fig, ax = plt.subplots(figsize=(8, 3.5))
        x = np.arange(len(preds))
        w = 0.27
        for k, (lab, vals) in enumerate([("screen LOBO", [s["lobo"][p]["mean_jsd"] for p in preds]),
                                          ("confirmation T1-T3", [c["c2b"].get("T1T2T3_bans", {}).get(p, {}).get("mean_jsd", np.nan) for p in preds]),
                                          ("T4 transfer", [c["c2b"].get("T4_transfer", {}).get(p, {}).get("mean_jsd", np.nan) for p in preds])]):
            ax.bar(x + (k - 1) * w, vals, w, label=lab)
        ax.set_xticks(x)
        ax.set_xticklabels([names[p] for p in preds])
        ax.set_ylabel("mean JSD (bits), lower = better")
        ax.legend(fontsize=7)
        ax.set_title("Predicting ban outcomes: one-scalar predictors, frozen before confirmation")
        fig.tight_layout()
        for ext in ("png", "pdf"):
            fig.savefig(FIG / f"predictor_jsd_bars.{ext}", dpi=150)
        plt.close(fig)
    rg = RES / "regularity.json"
    if rg.exists():
        r = json.loads(rg.read_text())
        cells = sorted(r["c2a"]["cells"], key=lambda x: -x["drop"])[:40]
        fig, ax = plt.subplots(figsize=(6, 0.18 * len(cells) + 1))
        yv = np.arange(len(cells))
        ax.barh(yv, [x["drop"] for x in cells], color=["C3" if x["violation"] else "C7" for x in cells])
        ax.scatter([x["noise_floor"] for x in cells], yv, marker="|", color="k", s=60, label="placebo noise floor")
        ax.set_yticks(yv)
        ax.set_yticklabels([f"{x['task']}/{x['cond']}: {x['idea']}" for x in cells], fontsize=6)
        ax.set_xlabel("share drop vs pooled placebo (red = Holm p<0.01 and > floor)")
        ax.legend(fontsize=7)
        fig.tight_layout()
        for ext in ("png", "pdf"):
            fig.savefig(FIG / f"regularity_forest.{ext}", dpi=150)
        plt.close(fig)
        fig, ax = plt.subplots(figsize=(5, 3))
        ks = ["A", "B", "C", "D", "D2", "D3", "E"]
        ax.bar(np.arange(len(ks)) - 0.2, [r["sign"][k]["sign_acc"] or 0 for k in ks], 0.4, label="sign acc")
        ax.bar(np.arange(len(ks)) + 0.2, [r["sign"][k]["balanced_sign_acc"] or 0 for k in ks], 0.4, label="balanced")
        ax.axhline(0.7, color="k", ls=":")
        ax.set_xticks(range(len(ks)))
        ax.set_xticklabels(ks)
        ax.legend(fontsize=7)
        ax.set_title("Sign of share change (|Δ|>=10pp), confirmation")
        fig.tight_layout()
        for ext in ("png", "pdf"):
            fig.savefig(FIG / f"sign_cells.{ext}", dpi=150)
        plt.close(fig)
    tp = RES / "transplant.json"
    if tp.exists():
        tr = json.loads(tp.read_text())
        bans = list(tr["bans"])
        fig, ax = plt.subplots(figsize=(8, 3.5))
        x = np.arange(len(bans))
        for k, (lab, key) in enumerate([("TRANSPLANT", "TRANSPLANT"), ("OFFTARGET", "OFFTARGET"), ("RAND (5-draw mean)", "RAND")]):
            vals, errs = [], []
            for b in bans:
                e = tr["bans"][b].get(key)
                v = (e or {}).get("R_mean" if key == "RAND" else "R", np.nan)
                lo, hi = (e or {}).get("ci95", [np.nan, np.nan])
                vals.append(v)
                errs.append([v - lo if lo is not None else 0, hi - v if hi is not None else 0])
            ax.bar(x + (k - 1) * 0.25, vals, 0.25, yerr=np.array(errs).T, label=lab, capsize=2)
        rest = [tr["bans"][b].get("RESTORE", {}).get("restoration", np.nan) for b in bans]
        ax.scatter(x, rest, marker="D", color="k", zorder=4, label="RESTORE (restoration)")
        ax.axhline(0, color="k", lw=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(bans, fontsize=7)
        ax.set_ylabel("recovery R")
        ax.legend(fontsize=7)
        ax.set_title("Suffix transplant of Δh at the first band layer (prefill only)")
        fig.tight_layout()
        for ext in ("png", "pdf"):
            fig.savefig(FIG / f"transplant_recovery.{ext}", dpi=150)
        plt.close(fig)
        e = tr["bans"].get("T1/ban_r1", {})
        pts = [(l, e.get(f"TRANSPLANT_L{l}", {}).get("R")) for l in (8, 18)] + [(frozen()["band"][0], e.get("TRANSPLANT", {}).get("R"))]
        pts = sorted([p for p in pts if p[1] is not None])
        if pts:
            fig, ax = plt.subplots(figsize=(4, 3))
            ax.plot([p[0] for p in pts], [p[1] for p in pts], "o-")
            ax.set_xlabel("layer of the suffix add")
            ax.set_ylabel("recovery R (T1 ban BFS)")
            fig.tight_layout()
            for ext in ("png", "pdf"):
                fig.savefig(FIG / f"layer_sweep.{ext}", dpi=150)
            plt.close(fig)
    es = RES / "edge_stat.json"
    if es.exists():
        ed = json.loads(es.read_text())
        items = [(k, v) for k, v in list(ed["screen"].items()) + list(ed["conf"].items()) if v["internal"]]
        fig, ax = plt.subplots(figsize=(6, 0.16 * len(items) + 1))
        yv = np.arange(len(items))
        E = [v["internal"]["E"] for _, v in items]
        lo = [v["internal"]["ci95"][0] for _, v in items]
        hi = [v["internal"]["ci95"][1] for _, v in items]
        ax.errorbar(E, yv, xerr=[np.array(E) - np.array(lo), np.array(hi) - np.array(E)], fmt="o", ms=3)
        ax.axvline(0, color="k", lw=0.5)
        ax.set_yticks(yv)
        ax.set_yticklabels([k for k, _ in items], fontsize=5)
        ax.set_xlabel("edge statistic E (>0 edge attraction, <0 far side)")
        fig.tight_layout()
        for ext in ("png", "pdf"):
            fig.savefig(FIG / f"edge_stat.{ext}", dpi=150)
        plt.close(fig)
    logger.info("figures written")


if __name__ == "__main__":
    what = sys.argv[1]
    fns = {"transplant": run_transplant, "edge": edge_stat, "lens": logit_lens, "manifold": manifold, "figures": figures}
    if what == "all":
        for k in ("edge", "lens", "manifold", "transplant", "figures"):
            fns[k]()
    else:
        fns[what]()
