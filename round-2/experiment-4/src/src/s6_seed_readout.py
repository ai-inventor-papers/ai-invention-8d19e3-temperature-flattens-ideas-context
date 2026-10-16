#!/usr/bin/env python3
"""STEP 6a: seed shocks (claim C3) - internal name-token utility readout + behavioural shock model + FREEZE.

--phase readout (GPU, HF transformers bf16):
  * opening prefixes: text before the first LEX_* match in baseline outputs (whitespace-normalised); top-3 exact
    prefixes per task and wording (grid: grid T=0.7 top-k none cell; P1: ban baseline n=300); coverage reported.
  * u_j(prompt, prefix) = logsumexp_v sum_t log p(name_v tokens | chat(prompt) + prefix); log-softmax over named
    ideas; u = frequency-weighted mean over the 3 prefixes.
  * contexts: unseeded grid + 60 screen seed strings (grid wording), unseeded P1 + 120 fresh strings (P1), forced
    P1 prompts (T7 sanity).
  * residual displacement per layer at the last 5 template tokens: seed vs base, ban_r1 vs placebo, placebo vs base.
--phase freeze (CPU): calibration gate (beta fit), screen Sigma (Ledoit-Wolf), behavioural Gaussian-shock model
  (fallback F4, pre-registered), engine noise from the 5 unseeded greedy repeats, per-string predictions for the
  fresh strings; writes results/frozen_c3_seeds.json (sha256) BEFORE any fresh seeded generation exists.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (INPUTS, LABELS_PATH, MODEL, NON_IDEAS, RESULTS, jsd_bits, read_jsonl, save_json,  # noqa: E402
                    setup_logging)

KIND = {"T1": "graph", "T2": "sort", "T3": "graph"}
GRAPH_IDEAS = ["BFS", "DFS", "IDDFS", "Dijkstra", "A_star", "Greedy_best_first", "Bidirectional", "Bellman_Ford",
               "SPFA", "Floyd_Warshall"]
SORT_IDEAS = ["Quick", "Merge", "Heap", "Insertion", "Selection", "Bubble", "Shell", "Counting", "Radix", "Bucket",
              "Tim_hybrid"]
NAMES = {
    "BFS": ["Breadth-First Search", "breadth-first search", "BFS", "Breadth First Search"],
    "DFS": ["Depth-First Search", "depth-first search", "DFS", "Depth First Search"],
    "IDDFS": ["Iterative Deepening Depth-First Search", "IDDFS", "iterative deepening"],
    "Dijkstra": ["Dijkstra's algorithm", "Dijkstra's Algorithm", "Dijkstra"],
    "A_star": ["A* search", "A* Search", "A*", "A-star"],
    "Greedy_best_first": ["Greedy Best-First Search", "greedy best-first search"],
    "Bidirectional": ["Bidirectional Search", "bidirectional search"],
    "Bellman_Ford": ["Bellman-Ford algorithm", "Bellman-Ford"],
    "SPFA": ["SPFA", "Shortest Path Faster Algorithm"],
    "Floyd_Warshall": ["Floyd-Warshall algorithm", "Floyd-Warshall"],
    "Quick": ["Quick Sort", "QuickSort", "Quicksort", "quicksort", "quick sort"],
    "Merge": ["Merge Sort", "merge sort", "MergeSort"], "Heap": ["Heap Sort", "heap sort"],
    "Insertion": ["Insertion Sort", "insertion sort"], "Selection": ["Selection Sort", "selection sort"],
    "Bubble": ["Bubble Sort", "bubble sort"], "Shell": ["Shell Sort", "shell sort"],
    "Counting": ["Counting Sort", "counting sort"], "Radix": ["Radix Sort", "radix sort"],
    "Bucket": ["Bucket Sort", "bucket sort"], "Tim_hybrid": ["Timsort", "TimSort", "Tim Sort"],
}
GRID_USER = {"T1": "Implement a path search algorithm in Python.", "T2": "Implement a sorting algorithm in Python.",
             "T3": "Implement a function in Python that finds the shortest path in a weighted graph with "
                   "non-negative edge weights."}


def ideas_of(task: str) -> list[str]:
    return GRAPH_IDEAS if KIND[task] == "graph" else SORT_IDEAS


def char_seed(rng: random.Random) -> str:
    return "".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(11))


def nouns() -> list[str]:
    src = (INPUTS / "grid" / "s0_setup.py").read_text()
    m = re.search(r'NOUNS = """(.*?)"""', src, re.S)
    return list(dict.fromkeys(m.group(1).split()))


def fresh_strings() -> list[dict]:
    rngc, rngw = random.Random(20261016), random.Random(20261017)
    nn = nouns()
    s = [dict(idx=i, kind="char", string=f"seed={char_seed(rngc)}") for i in range(60)]
    s += [dict(idx=60 + i, kind="word", string="seed=(" + " ".join(rngw.sample(nn, 4)) + ")") for i in range(60)]
    screen = {x["string"] for x in json.loads((INPUTS / "grid" / "config" / "seeds.json").read_text())["seeds"]}
    assert not ({x["string"] for x in s} & screen), "fresh strings overlap screen strings"
    assert len({x["string"] for x in s}) == 120
    return s


def opening_prefixes(texts: list[str], task: str) -> tuple[list[tuple[str, int]], float]:
    from activations import LEX_GRAPH, LEX_SORT
    lex = LEX_GRAPH if KIND[task] == "graph" else LEX_SORT
    pre = []
    for t in texts:
        m = lex.search(t)
        pre.append(" ".join(t[:m.start()].split()) if m else None)
    c = Counter(p for p in pre if p)
    top = c.most_common(3)
    return top, sum(v for _, v in top) / len(texts)


# ----------------------------------------------------------------------------- readout (GPU)
class Reader:
    def __init__(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(MODEL)
        self.model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16).cuda().eval()

    def chat(self, user: str) -> str:
        return self.tok.apply_chat_template([{"role": "user", "content": user}], tokenize=False,
                                            add_generation_prompt=True)

    def name_logprobs(self, context: str, ideas: list[str]) -> dict:
        """sum log p(variant tokens | context) for every variant; returns {idea: logsumexp over variants}."""
        torch = self.torch
        sep_space = context[-1:].isspace() or context.endswith(("**", "(", '"', "`"))
        ctx = context.rstrip() + (" " if context[-1:].isspace() else "")
        ctx_ids = self.tok(ctx.rstrip(" ") if context[-1:].isspace() else ctx, add_special_tokens=False)["input_ids"]
        seqs, owners = [], []
        for j in ideas:
            for v in NAMES[j]:
                vv = (" " + v) if (context[-1:].isspace() or not sep_space) and not context.endswith(
                    ("**", "(", '"', "`")) else v
                vids = self.tok(vv, add_special_tokens=False)["input_ids"]
                seqs.append((ctx_ids + vids, len(vids)))
                owners.append(j)
        L = max(len(s) for s, _ in seqs)
        ids = torch.full((len(seqs), L), self.tok.pad_token_id or 0, dtype=torch.long)
        att = torch.zeros((len(seqs), L), dtype=torch.long)
        for i, (s, _) in enumerate(seqs):
            ids[i, :len(s)] = torch.tensor(s)
            att[i, :len(s)] = 1
        with torch.no_grad():
            logits = self.model(input_ids=ids.cuda(), attention_mask=att.cuda()).logits.float()
            lp = torch.log_softmax(logits, -1)
        out: dict[str, list[float]] = {}
        for i, (s, nv) in enumerate(seqs):
            tot = 0.0
            for k in range(len(s) - nv, len(s)):
                tot += float(lp[i, k - 1, s[k]])
            out.setdefault(owners[i], []).append(tot)
        return {j: float(np.logaddexp.reduce(v)) for j, v in out.items()}

    def u_vector(self, user: str, prefixes: list[tuple[str, int]], ideas: list[str]) -> dict:
        base = self.chat(user)
        tot = sum(w for _, w in prefixes)
        acc = np.zeros(len(ideas))
        raw = []
        for p, w in prefixes:
            ctx = base + p + ("" if p.endswith(("**", "(")) else " ")
            r = self.name_logprobs(ctx, ideas)
            v = np.array([r[j] for j in ideas])
            v = v - np.logaddexp.reduce(v)   # log-softmax over named ideas
            raw.append(v.tolist())
            acc += w / tot * v
        return dict(u=acc.tolist(), per_prefix=raw)

    def last5_hidden(self, user: str) -> np.ndarray:
        torch = self.torch
        ids = self.tok(self.chat(user), add_special_tokens=False, return_tensors="pt")["input_ids"].cuda()
        with torch.no_grad():
            hs = self.model(input_ids=ids, output_hidden_states=True).hidden_states
        return np.stack([h[0, -5:].float().cpu().numpy() for h in hs])  # (L+1, 5, d)


def phase_readout() -> None:
    from protocol import user_message
    lab = read_jsonl(LABELS_PATH)
    gridtxt = {}
    for r in read_jsonl(INPUTS / "grid" / "data" / "raw_grid.jsonl"):
        if r["cond"] == "grid" and r["T"] == 0.7 and r["topk"] == -1:
            gridtxt.setdefault(r["task"], []).append(r["text"])
    p1txt = {t: [r["output_text"] for r in read_jsonl(INPUTS / "ban" / "gen" / t / "baseline.jsonl")]
             for t in ("T1", "T2", "T3")}
    rd = Reader()
    seeds_cfg = json.loads((INPUTS / "grid" / "config" / "seeds.json").read_text())
    # T4: seeded grid prompts render identically
    t4 = all(rd.chat(s["string"] + "\n\n" + GRID_USER[t]) == s["rendered"] for t in ("T1", "T2", "T3")
             for s in seeds_cfg["prompts"][t])
    logger.info(f"T4 seeded grid prompt rendering identical: {t4}")
    fresh = fresh_strings()
    out = dict(t4_seeded_render_ok=t4, name_variants=NAMES, prefixes={}, u={}, forced={}, fresh_strings=fresh)
    for t in ("T1", "T2", "T3"):
        ideas = ideas_of(t)
        pg, cg = opening_prefixes(gridtxt[t], t)
        pp, cp = opening_prefixes(p1txt[t], t)
        out["prefixes"][t] = dict(grid=dict(top3=pg, coverage=cg), P1=dict(top3=pp, coverage=cp))
        logger.info(f"{t}: prefix coverage grid={cg:.2f} P1={cp:.2f}")
        u = dict(ideas=ideas, grid_base=rd.u_vector(GRID_USER[t], pg, ideas),
                 P1_base=rd.u_vector(user_message(t, "baseline"), pp, ideas), screen={}, fresh={})
        for s in seeds_cfg["seeds"]:
            u["screen"][s["string"]] = rd.u_vector(s["string"] + "\n\n" + GRID_USER[t], pg, ideas)["u"]
        for s in fresh:
            u["fresh"][s["string"]] = rd.u_vector(s["string"] + "\n\n" + user_message(t, "baseline"), pp, ideas)["u"]
        out["u"][t] = u
        # T7 forced sanity
        hits = {}
        for j in ideas:
            fu = rd.u_vector(user_message(t, f"forced_{j}"), pp, ideas)["u"]
            hits[j] = ideas[int(np.argmax(fu))]
        out["forced"][t] = dict(argmax=hits, frac_correct=float(np.mean([hits[j] == j for j in ideas])))
        logger.info(f"{t}: T7 forced argmax correct {out['forced'][t]['frac_correct']:.2f}; P1 base argmax "
                    f"{ideas[int(np.argmax(u['P1_base']['u']))]}")
    save_json(RESULTS / "seed_readout.json", out)
    # residual displacement
    disp = {}
    for t in ("T1", "T2", "T3"):
        hb = rd.last5_hidden(GRID_USER[t])
        hs = [rd.last5_hidden(s["string"] + "\n\n" + GRID_USER[t]) for s in seeds_cfg["seeds"]]
        plan = json.loads((INPUTS / "ban" / "ban_plan.json").read_text())
        hp1 = rd.last5_hidden(user_message(t, "baseline"))
        hpl = rd.last5_hidden(user_message(t, "placebo"))
        hban = rd.last5_hidden(user_message(t, "ban_r1", plan[t]["ban_r1"]))
        dban = (hban - hpl).reshape(hb.shape[0], -1)
        seed_norm, cosv = [], []
        for h in hs:
            d = (h - hb).reshape(hb.shape[0], -1)
            seed_norm.append(np.linalg.norm(d, axis=1))
            cosv.append((d * dban).sum(1) / (np.linalg.norm(d, axis=1) * np.linalg.norm(dban, axis=1) + 1e-9))
        sn = np.mean(seed_norm, 0)
        bn = np.linalg.norm(dban, axis=1)
        pn = np.linalg.norm((hpl - hp1).reshape(hb.shape[0], -1), axis=1)
        disp[t] = dict(layers=list(range(hb.shape[0])), seed_minus_base=sn.tolist(), ban_minus_placebo=bn.tolist(),
                       placebo_minus_baseline=pn.tolist(), ratio_seed_over_ban=(sn / (bn + 1e-9)).tolist(),
                       cos_seed_vs_ban_mean=np.mean(cosv, 0).tolist())
    save_json(RESULTS / "seed_displacement.json", disp)
    logger.info("wrote results/seed_readout.json, results/seed_displacement.json")


# ----------------------------------------------------------------------------- freeze (CPU)
def softmax(x):
    x = np.asarray(x, float)
    e = np.exp(x - x.max())
    return e / e.sum()


def fit_beta(u: np.ndarray, counts: np.ndarray, T: float = 0.7) -> float:
    from scipy.optimize import minimize_scalar
    f = lambda b: -float((counts * np.log(softmax(b * u / T) + 1e-12)).sum())  # noqa: E731
    return float(minimize_scalar(f, bounds=(0.01, 20), method="bounded").x)


def mc_flip(u0: np.ndarray, cov: np.ndarray, ref: int, n: int = 100000, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    if np.allclose(cov, 0):
        return float(int(np.argmax(u0)) != ref)
    eps = rng.multivariate_normal(np.zeros(len(u0)), cov, size=n, method="eigh")
    return float((np.argmax(u0 + eps, 1) != ref).mean())


def behavioural_fit(u0: np.ndarray, greedy_labels: list[int], t07_labels: list[int], ref: int, seed: int = 0):
    """ML over an isotropic Gaussian shock scale s: greedy = argmax(u0+eps); T=0.7 sample ~ softmax(u0+eps)
    (u0 = log screen T=0.7 shares, so the 0.7 scale is already in u0)."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((20000, len(u0)))
    best = None
    grid = np.round(np.arange(0.0, 6.01, 0.1), 2)
    lls = []
    for s in grid:
        uu = u0 + s * z
        am = np.argmax(uu, 1)
        pg = np.bincount(am, minlength=len(u0)) / len(am)
        e = np.exp(uu - uu.max(1, keepdims=True))
        pt = (e / e.sum(1, keepdims=True)).mean(0)
        ll = sum(math.log(pg[g] + 1e-4) for g in greedy_labels) + sum(math.log(pt[t] + 1e-9) for t in t07_labels)
        lls.append(ll)
        if best is None or ll > best[1]:
            best = (float(s), ll)
    return dict(s_hat=best[0], loglik=best[1], grid=grid.tolist(), loglik_curve=lls)


def phase_freeze() -> None:
    from freeze import write_frozen
    ro = json.loads((RESULTS / "seed_readout.json").read_text())
    lab = read_jsonl(LABELS_PATH)
    body = dict(claim="C3 seed shocks: fresh-string greedy flip rate predicted within +/-0.10 (T1, T2); T3 flips < 5%",
                tolerance=0.10, t3_rule_max_flip=0.05, rng_seeds=dict(char=20261016, word=20261017),
                fresh_strings=ro["fresh_strings"], gate_rule="readout primary iff prefix coverage >= 0.25 AND "
                "JSD(after beta fit) <= 0.15 on BOTH wordings; else behavioural Gaussian-shock model (F4)",
                tasks={})
    for t in ("T1", "T2", "T3"):
        u = ro["u"][t]
        ideas = u["ideas"]
        tt = {}
        # observed screen distributions over named ideas
        g07 = Counter(r["label"] for r in lab if r["source"] == "grid" and r["cond"] == "grid" and r["task"] == t
                      and r["T"] == 0.7 and r["topk"] == -1)
        p1 = Counter(r["label"] for r in lab if r["source"] == "ban" and r["cond"] == "baseline" and r["task"] == t)
        cal = {}
        for name, base_u, obs in (("grid", u["grid_base"]["u"], g07), ("P1", u["P1_base"]["u"], p1)):
            cnt = np.array([obs.get(j, 0) for j in ideas], float)
            ub = np.array(base_u)
            b = fit_beta(ub, cnt)
            od = {j: c for j, c in zip(ideas, cnt) if c > 0}
            cal[name] = dict(beta=b, jsd_before=jsd_bits(dict(zip(ideas, softmax(ub / 0.7))), od),
                             jsd_after=jsd_bits(dict(zip(ideas, softmax(b * ub / 0.7))), od),
                             coverage=ro["prefixes"][t][name]["coverage"],
                             readout_argmax=ideas[int(np.argmax(ub))],
                             observed_mode=max(od, key=od.get) if od else None)
        gate = all(c["coverage"] >= 0.25 and c["jsd_after"] <= 0.15 for c in cal.values())
        tt["calibration"] = cal
        tt["gate_pass"] = gate
        # screen shocks (grid wording)
        ub = np.array(u["grid_base"]["u"])
        mode = int(np.argmax(ub))
        D = np.array([np.array(v) - ub for v in u["screen"].values()])
        Dc = D - D[:, [mode]]
        nm = [k for k in range(len(ideas)) if k != mode]
        from sklearn.covariance import LedoitWolf
        lw = LedoitWolf().fit(Dc[:, nm])
        Sig = np.zeros((len(ideas), len(ideas)))
        Sig[np.ix_(nm, nm)] = lw.covariance_
        tt["readout_screen"] = dict(mode=ideas[mode], sigma_seed=dict(zip([ideas[k] for k in nm],
                                                                         Dc[:, nm].std(0).tolist())),
                                    Sigma=Sig.tolist(), pop_pred_greedy_flip=mc_flip(ub - ub[mode], Sig, mode),
                                    per_string_flip_frac=float(np.mean([int(np.argmax(np.array(v))) != mode
                                                                        for v in u["screen"].values()])))
        # screen behavioural data (grid wording): greedy + T=0.7 seeded rows
        sg = {r["seed_string"]: r["label"] for r in lab if r["source"] == "seeds" and r["task"] == t
              and r["cond"] == "seed_greedy"}
        s7 = [r["label"] for r in lab if r["source"] == "seeds" and r["task"] == t and r["cond"] == "seed_t07"]
        ug = [r["label"] for r in lab if r["source"] == "grid" and r["task"] == t and r["cond"] == "greedy"][0]
        classes = sorted(set(g07) | set(sg.values()) | set(s7) | {ug})
        cnt07 = np.array([g07.get(c, 0) + 0.5 for c in classes])
        u0 = np.log(cnt07 / cnt07.sum())
        ref_g = classes.index(ug)
        bf = behavioural_fit(u0, [classes.index(x) for x in sg.values()], [classes.index(x) for x in s7], ref_g)
        tt["behavioural_screen"] = dict(classes=classes, u0=u0.tolist(), unseeded_greedy_grid=ug, **bf,
                                        observed_greedy_flip=float(np.mean([x != ug for x in sg.values()])),
                                        observed_t07_nonmode=float(np.mean([x != classes[int(np.argmax(u0))]
                                                                            for x in s7])))
        # engine noise from 5 unseeded P1 greedy repeats (re-draw)
        reps = [r["label"] for r in lab if r["source"] == "redraw" and r["task"] == t and r["cond"] == "greedy"]
        p1_greedy = Counter(reps).most_common(1)[0][0] if reps else None
        eng = 0.0 if len(set(reps)) <= 1 else float(1 - Counter(reps).most_common(1)[0][1] / len(reps))
        tt["engine"] = dict(unseeded_greedy_repeats=reps, unseeded_greedy_label=p1_greedy, disagreement=eng)
        # ---- predictions for fresh strings (P1 wording)
        upb = np.array(u["P1_base"]["u"])
        ref_ro = ideas.index(p1_greedy) if p1_greedy in ideas else int(np.argmax(upb))
        Sig_eng = np.eye(len(ideas)) * (eng * float(np.mean(np.diag(Sig)[nm])) if eng > 0 else 0.0)
        per = {}
        for s, v in u["fresh"].items():
            v = np.array(v)
            per[s] = dict(pred_greedy_idea=ideas[int(np.argmax(v))], p_flip=mc_flip(v, Sig_eng, ref_ro, 20000),
                          margin=float(np.sort(v)[-1] - np.sort(v)[-2]),
                          pred_t07_nonmode=float(1 - softmax(cal["P1"]["beta"] * v / 0.7)[ref_ro]),
                          shift_ref=float((v - upb)[ref_ro] - np.max(np.delete(v - upb, ref_ro))))
        ro_rate = float(np.mean([p["p_flip"] for p in per.values()]))
        p1cnt = np.array([p1.get(c, 0) + 0.5 for c in classes])
        u0p1 = np.log(p1cnt / p1cnt.sum())
        ref_b = classes.index(p1_greedy) if p1_greedy in classes else int(np.argmax(u0p1))
        beh_rate = mc_flip(u0p1, np.eye(len(classes)) * bf["s_hat"] ** 2, ref_b)
        beh_t07 = None
        if bf["s_hat"] > 0:
            rng = np.random.default_rng(1)
            uu = u0p1 + bf["s_hat"] * rng.standard_normal((20000, len(classes)))
            e = np.exp(uu - uu.max(1, keepdims=True))
            beh_t07 = float(1 - (e / e.sum(1, keepdims=True)).mean(0)[int(np.argmax(u0p1))])
        tt["predictions"] = dict(
            readout=dict(task_pred_greedy_flip=ro_rate, pop_pred_from_screen_Sigma=mc_flip(upb - upb[ref_ro], Sig,
                                                                                           ref_ro),
                         task_pred_t07_nonmode=float(np.mean([p["pred_t07_nonmode"] for p in per.values()])),
                         per_string=per),
            behavioural=dict(task_pred_greedy_flip=beh_rate, task_pred_t07_nonmode=beh_t07, classes=classes,
                             u0_P1=u0p1.tolist(), s_hat=bf["s_hat"]),
            primary="readout" if gate else "behavioural")
        prim = tt["predictions"][tt["predictions"]["primary"]]["task_pred_greedy_flip"]
        tt["predictions"]["primary_task_pred_greedy_flip"] = prim
        body["tasks"][t] = tt
        logger.info(f"{t}: gate={gate} cal={ {k: (round(v['coverage'], 2), round(v['jsd_after'], 3)) for k, v in cal.items()} } "
                    f"pred flip readout={ro_rate:.3f} behavioural={beh_rate:.3f} (s_hat={bf['s_hat']}) "
                    f"screen obs flip={tt['behavioural_screen']['observed_greedy_flip']:.3f}")
    write_frozen(RESULTS / "frozen_c3_seeds.json", body)


@logger.catch(reraise=True)
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=["readout", "freeze"])
    args = ap.parse_args()
    setup_logging(f"s6_seed_{args.phase}")
    if args.phase == "readout":
        phase_readout()
    else:
        if (RESULTS.parent / "gens" / "seeds_fresh.jsonl").exists():
            raise SystemExit("REFUSING to (re)freeze C3: fresh seeded generations already exist")
        phase_freeze()


if __name__ == "__main__":
    main()
