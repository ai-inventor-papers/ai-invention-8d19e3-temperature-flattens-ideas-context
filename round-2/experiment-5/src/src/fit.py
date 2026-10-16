#!/usr/bin/env python3
"""STEP 2 + 3: layer band (probe vs shuffled), centroids, massive-dim rule, external/lexical/co-mention
similarities, the seven predictors fitted by leave-one-ban-out on the 27 screen bans, and the FREEZE.

Outputs: results/band_selection.json, results/centroids_{task}.npz, results/delta_h_{task}.pt,
results/geometry_checks.json, results/predictor_scores_screen.json, results/frozen_predictors.json(+.sha256)
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geometry as GEO  # noqa: E402  (import first: it resets loguru sinks)
from loguru import logger  # noqa: E402
from classify import parse_list_names  # noqa: E402
from freeze import write_frozen  # noqa: E402
from protocol import MODEL, ROOT, TASK_KIND  # noqa: E402
from protocol_ext import DISPLAY_ALL, taxonomy  # noqa: E402
import predictors as PR  # noqa: E402

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
logger.add(ROOT / "logs" / "fit.log", rotation="30 MB", level="DEBUG")
RES = ROOT / "results"
ACTS = ROOT / "acts"
TASKS3 = ["T1", "T2", "T3"]
SCREEN_BANS = ["ban_r1", "ban_r2", "ban_r3", "ban_r4", "ban_top3", "ban_top5", "ban_rare", "para1_r1", "para2_r1"]
MIN_N = 8
FALLBACK_BAND = [29, 30, 31]
VARIANTS = ["G_suffix", "G_umean", "P_suffix", "P_umean"]


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def classes(task: str) -> list[str]:
    return taxonomy(task) + ["Unparseable"]


def counts_of(labels: list[str], K: list[str]) -> np.ndarray:
    c = Counter(labels)
    return np.array([c.get(k, 0) for k in K], float)


def screen_labels(task: str, cond: str) -> list[str]:
    return [r["label"] for r in load_jsonl(ROOT / "data" / "labels" / task / f"{cond}.jsonl")]


def forced_set(task: str, gen_dir: str = "gen") -> tuple[np.ndarray, list[str], list[str]]:
    """Window acts [n, L, d] (float16) + labels + source cond for all forced files of a task (stored + ext)."""
    Xs, ys, src = [], [], []
    for p in sorted((ACTS / gen_dir / task).glob("forced_*.npz")):
        z = np.load(p)
        c = p.stem
        labs = []
        for lp in (ROOT / "data" / "labels" / task / f"{c}.jsonl", ROOT / "data" / "conf" / "labels" / task / f"{c}.jsonl"):
            if lp.exists() and task != "T4":
                labs += load_jsonl(lp)
        if task == "T4":
            labs = load_jsonl(ROOT / "data" / "conf" / "labels" / "T4" / f"{c}.jsonl")
        assert [r["id"] for r in labs] == list(z["ids"]), f"id mismatch {task}/{c}"
        Xs.append(z["window"])
        ys += [r["label"] for r in labs]
        src += [c] * len(labs)
    return np.concatenate(Xs), ys, src


def baseline_set(task: str, gen_dir: str = "gen") -> tuple[np.ndarray, list[str]]:
    z = np.load(ACTS / gen_dir / task / "baseline.npz")
    lp = ROOT / "data" / ("labels" if task != "T4" else "conf/labels") / task / "baseline.jsonl"
    labs = load_jsonl(lp)
    assert [r["id"] for r in labs] == list(z["ids"])
    return z["window"], [r["label"] for r in labs]


# ------------------------------------------------------------------------------------------- band
def band_selection() -> dict:
    from joblib import Parallel, delayed
    data = {}
    for t in TASKS3:
        Xb, yb = baseline_set(t)
        Xf, yf, _ = forced_set(t)
        if t == "T3":
            X, y = Xf, np.array(yf)
        else:
            X, y = np.concatenate([Xb, Xf]), np.array(yb + yf)
        cnt = Counter(y)
        keep = [c for c, n in cnt.items() if n >= MIN_N and c != "Unparseable"]
        m = np.isin(y, keep)
        data[t] = (X[m], y[m], sorted(keep))
        logger.info(f"probe {t}: n={m.sum()} classes={sorted(keep)}")
    jobs = []
    for t, (X, y, _) in data.items():
        for li in range(X.shape[1]):
            Xl = X[:, li].astype(np.float32)
            jobs.append((t, li + 1, False, 0, Xl, y))
            for s in range(5):
                jobs.append((t, li + 1, True, s + 1, Xl, y))
    t0 = time.time()
    res = Parallel(n_jobs=40)(delayed(GEO._probe_one)(X, y, sd, sh) for (_, _, sh, sd, X, y) in jobs)
    logger.info(f"probe sweep: {len(jobs)} fits in {time.time() - t0:.0f}s")
    out = {t: {"classes": data[t][2], "n": int(len(data[t][1])), "real": {}, "shuffled": {}} for t in data}
    for (t, l, sh, sd, _, _), r in zip(jobs, res):
        if sh:
            out[t]["shuffled"].setdefault(str(l), []).append(r)
        else:
            out[t]["real"][str(l)] = r
    for t in out:
        out[t]["shuffled_p95"] = {l: float(np.percentile(v, 95)) for l, v in out[t]["shuffled"].items()}
        out[t]["score"] = {l: out[t]["real"][l] - out[t]["shuffled_p95"][l] for l in out[t]["real"]}
    nL = 35
    avg = np.array([np.mean([out[t]["score"][str(l)] for t in out]) for l in range(1, nL + 1)])
    win = np.array([avg[i:i + 3].mean() for i in range(nL - 2)])
    i = int(np.argmax(win))  # ties -> earliest
    band = [i + 1, i + 2, i + 3]
    fallback = bool(win[i] < 0.05)
    if fallback:
        band = FALLBACK_BAND
    out["avg_score"] = avg.tolist()
    out["window_score"] = win.tolist()
    out["band"] = band
    out["band_score"] = float(win[i])
    out["fallback_used"] = fallback
    logger.info(f"band = {band} (score {win[i]:.3f}, fallback={fallback})")
    return out


# ------------------------------------------------------------------------------------------- centroids
def band_mean_window(X: np.ndarray, band: list[int], layers: list[int] | None = None) -> np.ndarray:
    if layers is None:
        layers = list(range(1, 36))
    idx = [layers.index(l) for l in band]
    return X[:, idx].astype(np.float32).mean(1)


def prompt_states(task: str, kind: str = "screen") -> dict:
    z = np.load(ACTS / f"prompt_states_{kind}_{task}.npz")
    out: dict[str, dict] = {}
    for k in z.files:
        c, part = k.rsplit("__", 1)
        out.setdefault(c, {})[part] = z[k]
    return out


def build_centroids(task: str, band: list[int], ps: dict, gen_dir: str = "gen") -> dict:
    K = classes(task)
    Xb, yb = baseline_set(task, gen_dir)
    Xf, yf, _ = forced_set(task, gen_dir)
    Gb, Gf = band_mean_window(Xb, band), band_mean_window(Xf, band)
    X = np.concatenate([Gb, Gf])
    y = np.array(yb + yf)
    mu = X.mean(0)
    d = X.shape[1]
    cG = np.full((len(K), d), np.nan)
    cGn = np.full((len(K), d), np.nan)
    cGf = np.full((len(K), d), np.nan)
    nG = {}
    for j, c in enumerate(K):
        if c == "Unparseable":
            continue
        m = y == c
        nG[c] = int(m.sum())
        if m.sum() >= MIN_N:
            cG[j] = X[m].mean(0) - mu
        mn = np.array(yb) == c
        if mn.sum() >= MIN_N:
            cGn[j] = Gb[mn].mean(0) - Gb.mean(0)
        mf = np.array(yf) == c
        if mf.sum() >= MIN_N:
            cGf[j] = Gf[mf].mean(0) - Gf.mean(0)
    bidx = [l - 1 for l in band]
    fsuf = {c[len("forced_"):]: v["suf"][bidx].mean(0).mean(0) for c, v in ps.items() if c.startswith("forced_")}
    fum = {c[len("forced_"):]: v["umean"][bidx].mean(0) for c, v in ps.items() if c.startswith("forced_")}
    cP = np.full((len(K), d), np.nan)
    cPu = np.full((len(K), d), np.nan)
    if fsuf:
        ms, mu_ = np.mean(list(fsuf.values()), 0), np.mean(list(fum.values()), 0)
        for j, c in enumerate(K):
            if c in fsuf:
                cP[j] = fsuf[c] - ms
                cPu[j] = fum[c] - mu_
    return dict(classes=K, cG=cG, cG_nat=cGn, cG_forced=cGf, cP=cP, cPu=cPu, mu=mu, nG=nG, XG=X, yG=y)


def delta(ps: dict, cond: str, ref: str, band: list[int], variant: str) -> np.ndarray:
    bidx = [l - 1 for l in band]
    if variant.endswith("suffix"):
        return (ps[cond]["suf"][bidx].mean(0) - ps[ref]["suf"][bidx].mean(0)).mean(0)
    return ps[cond]["umean"][bidx].mean(0) - ps[ref]["umean"][bidx].mean(0)


def massive_dims(pss: dict, band: list[int]) -> dict:
    shares, sq = {}, {}
    for l in band:
        sh = []
        acc = 0
        for t in TASKS3:
            for c in SCREEN_BANS:
                dl = (pss[t][c]["suf"][l - 1] - pss[t]["placebo"]["suf"][l - 1]).mean(0)
                e = dl ** 2
                sh.append(float(np.sort(e)[-10:].sum() / e.sum()))
                acc = acc + e
        shares[l] = float(np.mean(sh))
        sq[l] = acc
    trig = any(v > 0.5 for v in shares.values())
    dims = sorted({int(i) for l in band for i in np.argsort(sq[l])[-10:]}) if trig else []
    top_any = {l: [int(i) for i in np.argsort(sq[l])[-10:][::-1]] for l in band}
    return dict(top10_share=shares, triggered=trig, zeroed_dims=dims, top10_dims=top_any)


# ------------------------------------------------------------------------------------------- external sims
def bge_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("BAAI/bge-base-en-v1.5", device="cpu")


def bge_class_emb(model, task: str, desc: dict) -> tuple[np.ndarray, np.ndarray]:
    K = classes(task)
    E = np.zeros((len(K), 768))
    valid = np.zeros(len(K), bool)
    texts, idx = [], []
    for j, c in enumerate(K):
        if c in desc and c in DISPLAY_ALL:
            texts.append(f"{DISPLAY_ALL[c]}: {desc[c]}")
            idx.append(j)
    em = model.encode(texts, normalize_embeddings=True)
    E[idx] = em
    valid[idx] = True
    return E, valid


def qwen_name_S(task: str) -> tuple[np.ndarray, np.ndarray]:
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
    K = classes(task)
    valid = np.array([c in DISPLAY_ALL for c in K])
    V = np.zeros((len(K), W.shape[1]))
    for j, c in enumerate(K):
        if valid[j]:
            V[j] = W[tok(DISPLAY_ALL[c], add_special_tokens=False)["input_ids"]].mean(0)
    V[valid] -= V[valid].mean(0)
    S = np.full((len(K), len(K)), np.nan)
    U = V[valid] / np.linalg.norm(V[valid], axis=1, keepdims=True)
    S[np.ix_(valid, valid)] = U @ U.T
    return S, valid


def comention_S(task: str) -> np.ndarray:
    from predictors import parse_select_list
    K = classes(task)
    if task == "T4":
        recs = load_jsonl(ROOT / "data" / "conf" / "gen" / "T4" / "comention.jsonl")
        lists = [parse_select_list(r["output_text"]) for r in recs]
    else:
        recs = load_jsonl(ROOT / "data" / "gen" / task / "comention.jsonl")
        lists = [parse_list_names(r["output_text"], TASK_KIND[task]) for r in recs]
    S = GEO.behavioural_S(lists, K)["pmi"]
    return S, lists


def q_share(task: str, lists: list[list[str]]) -> np.ndarray:
    K = classes(task)
    df = Counter(c for lst in lists for c in set(lst))
    q = np.array([df.get(c, 0) + 0.5 for c in K], float)
    return q / q.sum()


# ------------------------------------------------------------------------------------------- items
def make_item(task: str, cond: str, banned: list[str], counts: np.ndarray, counts0: np.ndarray, ctx: dict,
              ps: dict, ref: str, user_ban: str, user_ref: str) -> dict:
    K = classes(task)
    B = [K.index(c) for c in banned]
    s = {}
    for V in VARIANTS:
        C = ctx["cent"]["cG"] if V.startswith("G") else (ctx["cent"]["cP"] if V == "P_suffix" else ctx["cent"]["cPu"])
        dl = delta(ps, cond, ref, ctx["band"], V)
        dl[ctx["massive"]] = 0
        Cm = C.copy()
        Cm[:, ctx["massive"]] = 0
        s[f"B:{V}"] = PR.s_disp(dl, Cm, ctx["norms"][V])
    s["D"] = PR.s_sim(ctx["S_bge"], B, ctx["valid_bge"])
    e_b, e_r = ctx["bge"].encode([user_ban, user_ref], normalize_embeddings=True)
    s["D2"] = PR.s_disp(e_b - e_r, np.where(ctx["valid_bge"][:, None], ctx["E_bge"], np.nan), ctx["norms"]["D2"])
    s["D3"] = PR.s_sim(ctx["S_lex"], B, ctx["valid_lex"])
    s["E"] = np.nan_to_num(ctx["S_beh"][:, B].sum(1))
    return dict(task=task, cond=cond, banned=banned, B=B, counts=counts, counts0=counts0, q=ctx["q"], s=s,
                S=ctx["S_G"])


def with_variant(items: list[dict], V: str) -> list[dict]:
    out = []
    for it in items:
        it2 = dict(it)
        it2["s"] = dict(it["s"], B=it["s"][f"B:{V}"])
        out.append(it2)
    return out


def lobo(kind: str, items: list[dict], eps: float, groups: list[str] | None = None) -> tuple[list[dict], list]:
    per, preds = [], []
    keys = groups if groups is not None else list(range(len(items)))
    for i, it in enumerate(items):
        tr = [x for k, x in zip(keys, items) if k != keys[i]]
        kap = PR.fit_kappa(tr, eps)
        p = PR.fit_param(kind, tr, eps, kap)
        P_hat = PR.predict(kind, it, eps, kap, p)
        m = PR.metrics_one(P_hat, it, eps)
        m.update(task=it["task"], cond=it["cond"], param=p)
        per.append(m)
        preds.append(P_hat)
    return per, preds


def selftest(items: list[dict], eps: float) -> dict:
    """Synthetic beta recovery (n=100000 expected counts) + IIA identity + normalisation checks."""
    out = {}
    kap = PR.fit_kappa(items, eps)
    tr = with_variant(items, "G_suffix")
    for beta_true in (4.0, -3.0):
        syn = []
        for it in tr:
            P = PR.predict("B", it, eps, kap, beta_true)
            syn.append(dict(it, counts=np.round(P * 100000)))
        b_hat = PR.fit_param("B", syn, eps, PR.fit_kappa(syn, eps))
        out[f"beta_recovery_{beta_true}"] = b_hat
        assert abs(b_hat - beta_true) <= 0.1 * abs(beta_true) + 0.25, (beta_true, b_hat)
    it = dict(tr[0], B=[])
    Pt0 = PR.floor_P0(it["counts0"], it["q"], eps)
    assert np.allclose(PR.predict("A", it, eps, kap, 0.0), Pt0)
    for k in PR.PREDICTORS:
        for x in tr[:5]:
            p = PR.predict(k, dict(x, s=dict(x["s"])), eps, kap, 1.0 if k != "C" else 0.5)
            assert abs(p.sum() - 1) < 1e-9 and (p >= 0).all()
    obs_mass = np.mean([x["counts"][x["B"]].sum() / x["counts"].sum() for x in tr])
    pred_mass = np.mean([PR.predict("A", x, eps, kap, 0)[x["B"]].sum() for x in tr])
    out["compliance_obs_vs_pred_mean_banned_mass"] = [float(obs_mass), float(pred_mass)]
    out["iia_zero_banned_identity"] = True
    return out


def git_hash() -> str:
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@logger.catch(reraise=True)
def main() -> None:
    import torch
    RES.mkdir(exist_ok=True)
    bs_path = RES / "band_selection.json"
    if bs_path.exists():
        bsel = json.loads(bs_path.read_text())
    else:
        bsel = band_selection()
        bs_path.write_text(json.dumps(bsel, indent=1))
    band = bsel["band"]
    plan = json.loads((ROOT / "data" / "ban_plan.json").read_text())
    pss = {t: prompt_states(t) for t in TASKS3}
    mdim = massive_dims(pss, band)
    logger.info(f"massive dims: shares={mdim['top10_share']} triggered={mdim['triggered']}")
    massive = mdim["zeroed_dims"]
    norms = {}
    for V in VARIANTS:
        ns = []
        for t in TASKS3:
            for c in SCREEN_BANS:
                dl = delta(pss[t], c, "placebo", band, V)
                dl[massive] = 0
                ns.append(np.linalg.norm(dl))
        norms[V] = float(np.median(ns))
    desc = json.loads((ROOT / "src" / "descriptions.json").read_text())
    bge = bge_model()
    d2n = []
    geo_checks: dict = {"band": band, "massive": mdim, "norms": norms}
    ctxs = {}
    for t in TASKS3:
        cent = build_centroids(t, band, pss[t])
        K = cent["classes"]
        S_G = GEO.cos_matrix(np.where(np.isnan(cent["cG"]), np.nan, cent["cG"]))
        E_bge, valid_bge = bge_class_emb(bge, t, desc)
        S_bge = E_bge @ E_bge.T
        S_lex, valid_lex = qwen_name_S(t)
        S_beh, lists = comention_S(t)
        ctxs[t] = dict(cent=cent, band=band, massive=massive, norms=norms, S_G=S_G, E_bge=E_bge, valid_bge=valid_bge,
                       S_bge=S_bge, S_lex=S_lex, valid_lex=valid_lex, S_beh=S_beh, q=q_share(t, lists), bge=bge)
        for c in SCREEN_BANS:
            r = load_jsonl(ROOT / "data" / "gen" / t / f"{c}.jsonl")[0]
            rp = load_jsonl(ROOT / "data" / "gen" / t / "placebo.jsonl")[0]
            e = bge.encode([r["user_message"], rp["user_message"]], normalize_embeddings=True)
            d2n.append(float(np.linalg.norm(e[0] - e[1])))
        # geometry checks
        okc = [j for j in range(len(K)) if not np.isnan(cent["cG"][j, 0])]
        sh = GEO.split_half(cent["XG"], cent["yG"], [K[j] for j in okc])
        both = [j for j in okc if not np.isnan(cent["cG_nat"][j, 0]) and not np.isnan(cent["cG_forced"][j, 0])]
        agree = None
        if len(both) >= 3:
            from scipy.stats import spearmanr
            a = GEO.cos_matrix(cent["cG_nat"][both])
            b = GEO.cos_matrix(cent["cG_forced"][both])
            iu = np.triu_indices(len(both), 1)
            agree = float(spearmanr(a[iu], b[iu]).statistic)
        geo_checks[t] = dict(classes_with_G=[K[j] for j in okc], nG=cent["nG"], split_half=sh,
                             natural_vs_forced_spearman=agree, n_both=len(both),
                             S_G_symmetric=bool(np.allclose(np.nan_to_num(S_G), np.nan_to_num(S_G.T))),
                             S_G_diag=[float(S_G[j, j]) for j in okc])
        np.savez(RES / f"centroids_{t}.npz", classes=np.array(K), cG=cent["cG"], cG_nat=cent["cG_nat"],
                 cG_forced=cent["cG_forced"], cP=cent["cP"], cPu=cent["cPu"], mu=cent["mu"], S_G=S_G, S_bge=S_bge,
                 S_lex=S_lex, S_beh=S_beh, q=ctxs[t]["q"], band=np.array(band))
        dsave = {c: torch.tensor(pss[t][c]["suf"] - pss[t]["placebo"]["suf"]) for c in pss[t] if c != "placebo"}
        torch.save({k: v.half() for k, v in dsave.items()}, RES / f"delta_h_{t}.pt")
    norms["D2"] = float(np.median(d2n))
    items = []
    for t in TASKS3:
        c0 = counts_of(screen_labels(t, "placebo"), classes(t))
        rp = load_jsonl(ROOT / "data" / "gen" / t / "placebo.jsonl")[0]
        for c in SCREEN_BANS:
            r = load_jsonl(ROOT / "data" / "gen" / t / f"{c}.jsonl")[0]
            items.append(make_item(t, c, plan[t][c], counts_of(screen_labels(t, c), classes(t)), c0, ctxs[t],
                                   pss[t], "placebo", r["user_message"], rp["user_message"]))
    logger.info(f"{len(items)} screen ban items")
    eps = PR.fit_eps(items)
    logger.info(f"eps={eps}")
    geo_checks["selftest"] = selftest(items, eps)
    logger.info(f"selftest {geo_checks['selftest']}")
    scores: dict = {"eps": eps, "lobo": {}, "loto": {}, "per_ban": {}}
    for V in VARIANTS:
        iv = with_variant(items, V)
        per, _ = lobo("B", iv, eps)
        scores["lobo"][f"B:{V}"] = PR.summarize(per)
        scores["per_ban"][f"B:{V}"] = [dict(task=m["task"], cond=m["cond"], jsd=m["jsd"], param=m["param"]) for m in per]
        logger.info(f"LOBO B:{V} meanJSD={scores['lobo'][f'B:{V}']['mean_jsd']:.4f}")
    bestV = min(VARIANTS, key=lambda V: scores["lobo"][f"B:{V}"]["mean_jsd"])
    iv = with_variant(items, bestV)
    params = {}
    for k in PR.PREDICTORS:
        per, _ = lobo(k, iv, eps)
        scores["lobo"][k] = PR.summarize(per)
        scores["per_ban"][k] = [dict(task=m["task"], cond=m["cond"], jsd=m["jsd"], param=m["param"], loglik=m["loglik"],
                                     top_hit=m["top_hit"]) for m in per]
        perT, _ = lobo(k, iv, eps, groups=[it["task"] for it in iv])
        scores["loto"][k] = PR.summarize(perT)
        kap = PR.fit_kappa(iv, eps)
        params[k] = PR.fit_param(k, iv, eps, kap)
        logger.info(f"{k}: LOBO meanJSD={scores['lobo'][k]['mean_jsd']:.4f} LOTO={scores['loto'][k]['mean_jsd']:.4f} "
                    f"param(all)={params[k]}")
    kappa = PR.fit_kappa(iv, eps)
    scores["chosen_variant"] = bestV
    scores["params_all"] = params
    scores["kappa"] = kappa
    (RES / "predictor_scores_screen.json").write_text(json.dumps(scores, indent=1))
    (RES / "geometry_checks.json").write_text(json.dumps(geo_checks, indent=1, default=float))
    subprocess.run(["git", "-C", str(ROOT), "add", "src", "results/band_selection.json",
                    "results/predictor_scores_screen.json", "results/geometry_checks.json"], check=True)
    subprocess.run(["git", "-C", str(ROOT), "commit", "-qm", "Screen fit (pre-freeze)"], check=False)
    frozen = dict(band=band, variant=bestV, beta=params["B"], lambda_nested=params["C"], beta_D=params["D"],
                  beta_D2=params["D2"], beta_D3=params["D3"], beta_E=params["E"], eps=eps, kappa=kappa,
                  massive_dims=massive, norms=norms, sign_rule="sign(P_hat_B(j) - Ptil0(j))",
                  centroid_sha256={t: sha_file(RES / f"centroids_{t}.npz") for t in TASKS3},
                  descriptions_sha256=sha_file(ROOT / "src" / "descriptions.json"), code_git_hash=git_hash(),
                  timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                  screen_lobo_mean_jsd={k: scores["lobo"][k]["mean_jsd"] for k in PR.PREDICTORS})
    h = write_frozen(RES / "frozen_predictors.json", frozen, "FREEZE predictors before any confirmation generation")
    logger.info(f"FROZEN predictors sha256={h}")


if __name__ == "__main__":
    main()
