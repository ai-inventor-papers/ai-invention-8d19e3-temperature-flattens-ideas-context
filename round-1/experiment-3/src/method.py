#!/usr/bin/env python3
"""INFLUENCE ARM: can internal knobs (H-flatten, A3 menu erasure, A4 unusualness dial) beat temperature
and prompting for novel-but-correct path-search code on Qwen2.5-3B-Instruct?

Stages (each resumable; run in order):
  baseline  : T=0.7 plain, n=300 on T1/T3 (+score)
  acts      : teacher-forced residual cache (prompt-final, gen1..8, mean gen1..32; all 37 hidden states)
  probes    : per-layer multinomial idea probes (5-fold CV, within-task shuffled control) -> band
  vectors   : H-probe, H-dim, A3 bases, LEACE, random controls, A4 direction (+ checks)
  calib     : strength calibration on T1 (n=20) -> calibration.json (frozen) + rules.json
  sweep     : full sweep (internal knobs + controls + temperature + prompts + gen-then-select)
  select    : pick best eligible setting per family -> heldout_plan.json
  heldout   : fresh seeds 1000..1099 for candidates + matched controls
  judge     : OpenRouter judge (outside-menu novelty + classifier audit), cap $1.5
  analyze   : metrics, CIs, survival verdicts, figures, method_out.json
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import random
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from loguru import logger  # noqa: E402

from protocol.prompts import (DISPLAY_NAME, MAX_NEW_TOKENS, MODEL_ID, TASKS, build_user_prompt,  # noqa: E402
                              gts_stage1_prompt, gts_stage2_prompt, write_protocol_json)
from src.common import (ACTS, CAPS, GENS, RES, SCORED, VEC, Scorer, append_jsonl, read_jsonl,  # noqa: E402
                        set_ram_limit, setup_logging)
from src.acts_io import load_acts, save_split  # noqa: E402
from src.settings import Setting, build_main_settings, gts_settings, spec_key  # noqa: E402

CTX_PATH = RES / "context.json"
N_BASE = 300
CALIB_GRID = [0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0]
BAN_DEFAULTS = {"T1": ["bfs", "dfs", "dijkstra"], "T3": ["dijkstra", "bellman_ford", "astar"]}
NONIDEA = {"no_code", "syntax_error"}


def load_ctx() -> dict:
    return json.loads(CTX_PATH.read_text()) if CTX_PATH.exists() else {}


def save_ctx(ctx: dict) -> None:
    CTX_PATH.write_text(json.dumps(ctx, indent=2))


def scored(task: str, setting: str) -> list[dict]:
    return read_jsonl(SCORED / task / f"{setting}.jsonl")


# ----------------------------------------------------------------------------------------------- GPU runner
class Runner:
    def __init__(self, batch_size: int = 192):
        import torch
        self.torch = torch
        self.model = None
        self.B = batch_size
        self.ctx = load_ctx()
        self.iv_cache: dict = {}
        self.vec = None
        self.scorer = Scorer()
        self.pool = ThreadPoolExecutor(1)
        self.pending = []
        self.gts_lists: dict = {}

    # -------------------------------------------------------------- interventions
    def _vectors(self) -> dict:
        if self.vec is None:
            import torch
            self.vec = torch.load(VEC / "vectors.pt", map_location="cuda", weights_only=False)  # self-generated file
            if "leace" not in self.vec:  # erasers live in their own file (size limit)
                self.vec["leace"] = {t: torch.load(VEC / f"leace_{t}.pt", map_location="cuda", weights_only=False)
                                     for t in ("T1", "T3")}
        return self.vec

    def intervention(self, task: str, iv: dict):
        from src.engine import Intervention
        if not iv:
            return Intervention()
        key = spec_key(task, iv)
        if key in self.iv_cache:
            return self.iv_cache[key]
        V = self._vectors()
        band = self.ctx["band"]
        med = self.ctx["median_norm"]
        if iv["kind"] == "add":
            name = iv["vec"]
            vecs = {}
            for l in band:
                if name == "A4":
                    v = V["A4"][l]
                elif name.startswith("rand"):
                    v = V["rand_add"][l][int(name[4:])]
                else:
                    v = V[name][task][l]
                vecs[l] = (iv["alpha"] * med[str(l)] / len(band)) * v
            out = Intervention(kind="add", vecs=vecs)
        elif iv["kind"] == "project":
            r = iv["r"]
            Us, mus = {}, {}
            for l in band:
                if iv["basis"] == "A3":
                    Us[l] = V["A3_U"][task][l][:, :r].contiguous()
                else:
                    Us[l] = V["rand_proj"][l][int(iv["basis"][4:])][:, :r].contiguous()
                mus[l] = V["mu"][task][l]
            out = Intervention(kind="project", U=Us, mu=mus, a=iv["a"])
        elif iv["kind"] == "leace":
            out = Intervention(kind="leace", eraser={l: V["leace"][task][l] for l in band}, a=iv["a"])
        else:
            raise ValueError(iv)
        self.iv_cache[key] = out
        return out

    # -------------------------------------------------------------- prompts
    def prompt_for(self, s: Setting, idx: int) -> tuple[str, int, dict]:
        """Returns (user_prompt, seed, extra)."""
        if s.cond in ("plain", "new", "novel2000"):
            return build_user_prompt(s.task, s.cond), idx, {}
        if s.cond == "ban3":
            return build_user_prompt(s.task, "ban3", cond_text=self.ctx["ban3_text"][s.task]), idx, {}
        if s.cond == "gts_list":
            return gts_stage1_prompt(s.task), idx, {}
        if s.cond == "gts":
            if s.task not in self.gts_lists:
                self.gts_lists[s.task] = {r["idx"]: r for r in read_jsonl(GENS / s.task / f"{s.name}_list.jsonl")}
            lst = self.gts_lists[s.task]
            items = parse_numbered(lst[idx]["text"]) if idx in lst else []
            if not items:
                return build_user_prompt(s.task), idx + 100000, {"gts_item": None, "gts_n_items": 0}
            pick = random.Random(idx).randrange(len(items))
            return gts_stage2_prompt(s.task, items[pick]), idx + 100000, {"gts_item": items[pick],
                                                                          "gts_n_items": len(items), "gts_pick": pick}
        raise ValueError(s.cond)

    # -------------------------------------------------------------- main loop
    def run(self, settings: list[Setting], tag: str) -> None:
        from src.engine import generate_batch, free
        jobs = []
        for s in settings:  # score backlog (generations written but not scored, e.g. after an interruption)
            if s.name.endswith("_list"):
                continue
            g = read_jsonl(GENS / s.task / f"{s.name}.jsonl")
            sdone = {r["idx"] for r in read_jsonl(SCORED / s.task / f"{s.name}.jsonl")}
            back = [r for r in g if r["idx"] not in sdone]
            if back:
                logger.info(f"scoring backlog {s.task}/{s.name}: {len(back)}")
                self._score(s.task, s.name, back)
        for s in settings:
            done = {r["idx"] for r in read_jsonl(GENS / s.task / f"{s.name}.jsonl")}
            jobs += [(s, i) for i in s.indices if i not in done]
        logger.info(f"[{tag}] {len(jobs)} jobs over {len(settings)} settings (batch {self.B})")
        if not jobs:
            return
        if self.model is None:
            from src.engine import Steerer, backtick_token_ids, load_model
            self.tok, self.model = load_model(MODEL_ID)
            self.ticks = backtick_token_ids(self.tok)
            band = self.ctx.get("band")
            cap = (band + [max(band) + 2]) if band else []
            # F4: choice commits after gen8 -> hook window prompt-final + gen1..64
            self.steerer = Steerer(self.model, window=64, capture_layers=cap)
        t_start = time.time()
        n_done = 0
        bi = 0
        while bi < len(jobs):
            batch = jobs[bi:bi + self.B]
            prompts, seeds, extras = [], [], []
            for s, i in batch:
                p, sd, ex = self.prompt_for(s, i)
                prompts.append(p)
                seeds.append(sd)
                extras.append(ex)
            ivs = [self.intervention(s.task, s.iv) for s, _ in batch]
            try:
                res = generate_batch(self.tok, self.model, prompts, seeds, [s.T for s, _ in batch],
                                     [s.topk for s, _ in batch], ivs, [s.code_stop for s, _ in batch], self.steerer,
                                     self.ticks, max_new=MAX_NEW_TOKENS)
            except self.torch.cuda.OutOfMemoryError:
                free()
                self.B = max(8, self.B // 2)
                logger.warning(f"OOM -> batch {self.B}")
                continue
            bi += len(batch)
            n_done += len(batch)
            recs_by = defaultdict(list)
            caps_by = defaultdict(list)
            for j, (s, i) in enumerate(batch):
                rec = {"setting": s.name, "family": s.family, "task": s.task, "idx": i, "seed": seeds[j],
                       "T": s.T, "topk": s.topk, "iv": s.iv, "prompt": prompts[j], "text": res["texts"][j],
                       "ntoks": res["ntoks"][j], "hit_max": res["hit_max"][j], "gen_ids32": res["ids32"][j],
                       "batch_seconds": round(res["seconds"], 2), **extras[j]}
                recs_by[(s.task, s.name)].append(rec)
                caps_by[(s.task, s.name)].append(j)
            for (task, name), recs in recs_by.items():
                append_jsonl(GENS / task / f"{name}.jsonl", recs)
                if res["captured"]:
                    rows = caps_by[(task, name)]
                    arrs = {f"m8_{l}": v[0][rows] for l, v in res["captured"].items()}
                    arrs.update({f"m32_{l}": v[1][rows] for l, v in res["captured"].items()})
                    d = CAPS / task / name
                    d.mkdir(parents=True, exist_ok=True)
                    np.savez(d / f"b{int(time.time() * 1000)}.npz", idx=np.array([r["idx"] for r in recs]), **arrs)
                if not name.endswith("_list"):
                    self.pending.append(self.pool.submit(self._score, task, name, recs))
            el = time.time() - t_start
            logger.info(f"[{tag}] {n_done}/{len(jobs)} gens, batch {res['seconds']:.1f}s, "
                        f"elapsed {el / 60:.1f} min, ETA {el / n_done * (len(jobs) - n_done) / 60:.1f} min")
        for f in self.pending:
            f.result()
        self.pending = []

    def _score(self, task: str, name: str, recs: list[dict]) -> None:
        try:
            out = self.scorer.score_records(recs)
            append_jsonl(SCORED / task / f"{name}.jsonl", out)
        except Exception:
            logger.exception(f"scoring failed for {task}/{name}")
            raise


def parse_numbered(text: str) -> list[str]:
    items = []
    for line in text.splitlines():
        m = re.match(r"^\s*(?:\*\*)?(\d{1,2})[\.\)]\s*(.+?)\s*$", line)
        if m:
            it = re.sub(r"\*\*|__|`", "", m.group(2)).strip()
            if len(it) > 3:
                items.append(it[:300])
    return items[:10]


# ----------------------------------------------------------------------------------------------- stages
def stage_baseline(args) -> None:
    write_protocol_json(ROOT / "protocol" / "protocol.json")
    run = Runner(args.batch)
    S = [Setting("baseline", "baseline", t, indices=list(range(args.n_base))) for t in ("T1", "T3")]
    run.run(S, "baseline")
    ctx = load_ctx()
    ctx["menus"], ctx["k"], ctx["ban3"], ctx["ban3_text"], ctx["base_share"] = {}, {}, {}, {}, {}
    for t in ("T1", "T3"):
        sc = scored(t, "baseline")
        cnt = Counter(r["label"] for r in sc)
        n = len(sc)
        # menu = named known algorithms only ('other'/'random_walk' are the outside-menu pool, not an idea)
        valid = {c: v for c, v in cnt.items() if c not in NONIDEA | {"other", "random_walk"}}
        menu = sorted([c for c, v in valid.items() if v / n >= 0.03], key=lambda c: -valid[c])
        note = ">=3%"
        if len(menu) < 2:
            menu = sorted([c for c, v in valid.items() if v / n >= 0.01], key=lambda c: -valid[c])
            note = ">=1% (fallback F3: menu too narrow at 3%)"
        ctx["menus"][t] = {"classes": menu, "rule": note}
        ctx["k"][t] = len(menu)
        top = [c for c, _ in sorted(valid.items(), key=lambda x: -x[1]) if c not in ("other", "random_walk")][:3]
        for c in BAN_DEFAULTS[t]:
            if len(top) < 3 and c not in top:
                top.append(c)
        ctx["ban3"][t] = top
        ctx["ban3_text"][t] = "Do not use any of the following algorithms: {}, {}, {}.".format(
            *[DISPLAY_NAME[c] for c in top])
        ctx["base_share"][t] = {c: v / n for c, v in cnt.most_common()}
        logger.info(f"{t}: n={n} counts={dict(cnt.most_common())} pass={np.mean([r['pass'] for r in sc]):.3f} "
                    f"menu={menu} ban3={top}")
    save_ctx(ctx)
    write_protocol_json(ROOT / "protocol" / "protocol.json", extra={"ban3_text": ctx["ban3_text"], "menus": ctx["menus"]})


def stage_acts(args) -> None:
    import torch
    from src.engine import load_model, render
    tok, model = load_model(MODEL_ID)
    for t in ("T1", "T3"):
        recs = sorted(read_jsonl(GENS / t / "baseline.jsonl"), key=lambda r: r["idx"])
        mm = np.zeros((len(recs), 10, 37, 2048), dtype=np.float16)  # 434 MB in RAM; saved as <100 MB parts
        lens = []
        bs = 32
        for b in range(0, len(recs), bs):
            chunk = recs[b:b + bs]
            p_ids = [tok(render(tok, r["prompt"]), add_special_tokens=False)["input_ids"] for r in chunk]
            g_ids = [r["gen_ids32"] for r in chunk]
            seqs = [p + g for p, g in zip(p_ids, g_ids)]
            L = max(len(s) for s in seqs)
            ids = torch.full((len(seqs), L), tok.pad_token_id, dtype=torch.long)
            att = torch.zeros((len(seqs), L), dtype=torch.long)
            for i, s in enumerate(seqs):
                ids[i, L - len(s):] = torch.tensor(s)
                att[i, L - len(s):] = 1
            with torch.inference_mode():
                hs = model(input_ids=ids.cuda(), attention_mask=att.cuda(), output_hidden_states=True).hidden_states
            H = torch.stack(hs, dim=2)  # [B, L, 37, d]
            for i, (p, g) in enumerate(zip(p_ids, g_ids)):
                pf = L - len(g) - 1
                ng = len(g)
                lens.append(ng)
                sel = [pf] + [pf + k for k in range(1, 9)]
                sel = [min(x, L - 1) for x in sel]
                block = H[i, sel].float()
                m32 = H[i, pf + 1:pf + 1 + ng].float().mean(0, keepdim=True) if ng > 0 else H[i, pf:pf + 1].float()
                mm[b + i] = torch.cat([block, m32], 0).cpu().numpy().astype(np.float16)
            del hs, H
            torch.cuda.empty_cache()
        parts = save_split(mm, ACTS, t)
        del mm
        logger.info(f"acts {t}: saved {len(parts)} parts ; gen lens min={min(lens)}")
        np.save(ACTS / f"baseline_{t}_idx.npy", np.array([r["idx"] for r in recs]))
    # sanity: prompt-final residual identical within task
    a = load_acts(ACTS, "T1")
    logger.info(f"prompt-final identical across samples (T1, layer 20): "
                f"{bool(np.allclose(a[0, 0, 20], a[17, 0, 20], atol=1e-2))}")


def _probe_labels(ctx: dict) -> tuple[np.ndarray, np.ndarray, list[str]]:
    classes = sorted(set(ctx["menus"]["T1"]["classes"]) | set(ctx["menus"]["T3"]["classes"]))
    ys, ts = [], []
    for t in ("T1", "T3"):
        idx = np.load(ACTS / f"baseline_{t}_idx.npy")
        lab = {r["idx"]: r["label"] for r in scored(t, "baseline")}
        for i in idx:
            c = lab[int(i)]
            ys.append(c if c in classes else "rare")
            ts.append(t)
    names = classes + (["rare"] if "rare" in ys else [])
    return np.array([names.index(y) for y in ys]), np.array(ts), names


def stage_probes(args) -> None:
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor
    from src.probes import probe_layer
    ctx = load_ctx()
    y, tasks, names = _probe_labels(ctx)
    ctx["probe_classes"] = names
    save_ctx(ctx)
    jobs = list(range(37))
    results = [None] * 37
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=mp.get_context("spawn")) as ex:
        futs = {ex.submit(probe_layer, str(ACTS), l, y.tolist(), tasks.tolist()): l for l in jobs}
        for f in futs:
            l = futs[f]
            results[l] = f.result()
            logger.info(f"probe layer {l}: bal={results[l]['bal_acc_pooled']:.3f} "
                        f"shuf={results[l]['shuf_bal_acc_pooled']:.3f} C={results[l]['C']}")
    gap = np.array([r["bal_acc_pooled"] - r["shuf_bal_acc_pooled"] for r in results])
    best, band = -1e9, None
    for start in range(4, 33 - 2):
        m = gap[start:start + 3].mean()
        if m > best:
            best, band = m, [start, start + 1, start + 2]
    ctx = load_ctx()
    ctx["band"] = band
    ctx["probe_C"] = {str(l): results[l]["C"] for l in range(37)}
    save_ctx(ctx)
    maj = {}
    for t in ("T1", "T3"):
        yt = y[tasks == t]
        maj[t] = float(np.bincount(yt).max() / len(yt))
    out = {"layers": results, "band": band, "band_mean_gap": float(best), "classes": names, "majority": maj,
           "prompt_final_note": ("prefill is deterministic, so the prompt-final residual is identical for all samples "
                                 "of a task: a within-task probe there is at the majority baseline by construction")}
    (RES / "probe_curve.json").write_text(json.dumps(out, indent=2))
    logger.info(f"band = {band} (mean gap {best:.3f})")


def stage_vectors(args) -> None:
    from src.vectors import build_vectors
    build_vectors(load_ctx(), save_ctx)


def stage_calib(args) -> None:
    ctx = load_ctx()
    run = Runner(args.batch)
    S = []
    knobs = [("Hprobe", "H-probe"), ("Hdim", "H-dim"), ("A4", "A4")]
    for knob, fam in knobs:
        for a in CALIB_GRID:
            S.append(Setting(f"calib_{knob}_a{a:g}", fam, "T1", iv={"kind": "add", "vec": knob, "alpha": a},
                             indices=list(range(args.n_calib))))
    run.run(S, "calib")
    base = np.mean([r["pass"] for r in scored("T1", "baseline")])
    calib = {"baseline_pass_T1": float(base), "grid": CALIB_GRID, "n": args.n_calib, "knobs": {}}
    alphas = {}
    for knob, _ in knobs:
        rows = []
        for a in CALIB_GRID:
            sc = scored("T1", f"calib_{knob}_a{a:g}")
            pr = float(np.mean([r["pass"] for r in sc])) if sc else float("nan")
            labs = Counter(r["label"] for r in sc)
            rows.append({"alpha": a, "pass": pr, "labels": dict(labs),
                         "degenerate": float(np.mean([r["deg_no_code"] or r["deg_syntax_error"] or r["deg_looping"]
                                                      for r in sc])) if sc else None})
        safe = [r["alpha"] for r in rows if r["pass"] >= 0.95 * base]
        lo = max(safe) if safe else CALIB_GRID[0]
        broken = [r["alpha"] for r in rows if r["alpha"] > lo and r["pass"] <= 0.4 * base]
        hi = min(broken) if broken else CALIB_GRID[-1]
        if hi <= lo:
            hi = CALIB_GRID[-1]
        lo_eff = lo if hi > lo else CALIB_GRID[0]
        pts = list(np.geomspace(lo_eff, hi, 5)) if hi > lo_eff else list(np.geomspace(CALIB_GRID[0], CALIB_GRID[-1], 5))
        pts = [float(f"{p:.3g}") for p in pts]
        alphas[knob] = pts
        calib["knobs"][knob] = {"rows": rows, "alpha_lo": lo, "alpha_hi": hi, "chosen": pts}
        logger.info(f"calib {knob}: " + ", ".join(f"{r['alpha']}:{r['pass']:.2f}" for r in rows) + f" -> {pts}")
    calib["rule"] = ("alpha_lo = largest grid alpha with pass >= 0.95*baseline; alpha_hi = smallest larger alpha with "
                     "pass <= 0.40*baseline (else grid max); 5 strengths geometric in [alpha_lo, alpha_hi]; frozen "
                     "before the full run and reused for T3 and the matched random controls")
    (RES / "calibration.json").write_text(json.dumps(calib, indent=2))
    ctx = load_ctx()
    ctx["alphas"] = alphas
    save_ctx(ctx)
    rules = {
        "eligibility": "pass_rate >= 0.8 * baseline pass_rate (per task; pooled T1+T3 for decisions)",
        "selection": "best-of-method = eligible setting with highest target metric on indices 0..99; survival "
                     "decided on fresh seeds 1000..1099 (held-out draw) to remove winner's-curse bias",
        "H": "entropy(best H) >= 2 x entropy(best eligible temperature) on held-out AND bootstrap 95% CI of "
             "entropy(H) - entropy(R-add at same alpha) excludes 0; checked on T1 and pooled, T3 reported",
        "A3": "outside_menu_correct_share(best A3) >= 3 x max over (temperature, new, novel2000, ban3) AND >= 0.05 "
              "absolute AND CI vs R-proj excludes 0",
        "A4": "Spearman(alpha in {0,a1..a5}, atypicality) >= 0.8 on BOTH T1 and T3, atypicality = mean -log p0(label) "
              "with add-0.5 smoothing, AND beats R-add at top strength (CI excludes 0)",
        "fallback": "if nothing survives: headline = prompting ceiling, naming the prompt method atop each front",
        "written_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (RES / "rules.json").write_text(json.dumps(rules, indent=2))


def stage_sweep(args) -> None:
    ctx = load_ctx()
    run = Runner(args.batch)
    pri = {"temperature": 0, "prompt": 0, "crn": 1, "H-probe": 2, "H-dim": 2, "R-add": 3, "A3-proj": 4,
           "A3-leace": 4, "R-proj": 5, "A4": 6, "gts": 7}
    S = []
    for t in ("T1", "T3"):
        S += build_main_settings(ctx, t, n_main=args.n_main, n_ctrl=args.n_ctrl)
    if args.only:
        S = [s for s in S if re.search(args.only, s.name)]
    S.sort(key=lambda s: pri.get(s.family, 9))
    (RES / "sweep_settings.json").write_text(json.dumps([s.to_dict() for s in S], indent=1))
    run.run(S, "sweep")
    if not args.skip_gts:
        G = []
        for t in ("T1", "T3"):
            G += gts_settings(t, list(range(args.n_main)))
        run.run([g for g in G if g.cond == "gts_list"], "gts1")
        run.run([g for g in G if g.cond == "gts"], "gts2")


def stage_heldout(args) -> None:
    plan = json.loads((RES / "heldout_plan.json").read_text())
    run = Runner(args.batch)
    S = []
    for d in plan["settings"]:
        S.append(Setting(**{**d, "indices": list(range(1000, 1000 + args.n_heldout))}))
    run.run(S, "heldout")


def stage_explore(args) -> None:
    """POST-HOC exploratory supplement (NOT used by the pre-registered survival rules): H-probe / H-dim below the
    frozen calibrated strengths, to locate the flattening point between 'no effect' and 'mode flip'."""
    run = Runner(args.batch)
    S = []
    for t in ("T1", "T3"):
        for a in (0.1, 0.2, 0.35, 0.5):
            S.append(Setting(f"Hprobe_x_a{a:g}", "H-probe-explore", t, iv={"kind": "add", "vec": "Hprobe", "alpha": a},
                             indices=list(range(args.n_main)), params={"alpha": a, "post_hoc": True}))
        S.append(Setting("Hdim_x_a0.075", "H-dim-explore", t, iv={"kind": "add", "vec": "Hdim", "alpha": 0.075},
                         indices=list(range(args.n_main)), params={"alpha": 0.075, "post_hoc": True}))
    (RES / "explore_settings.json").write_text(json.dumps([s.to_dict() for s in S], indent=1))
    run.run(S, "explore")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage")
    ap.add_argument("--batch", type=int, default=192)
    ap.add_argument("--n_base", type=int, default=N_BASE)
    ap.add_argument("--n_calib", type=int, default=20)
    ap.add_argument("--n_main", type=int, default=100)
    ap.add_argument("--n_ctrl", type=int, default=50)
    ap.add_argument("--n_heldout", type=int, default=100)
    ap.add_argument("--workers", type=int, default=18)
    ap.add_argument("--only", default="")
    ap.add_argument("--skip_gts", action="store_true")
    args = ap.parse_args()
    setup_logging(f"method_{args.stage}")
    if args.stage in ("probes", "select", "judge", "analyze"):  # CPU-only stages: hard RAM cap (cgroup is 57 GB)
        set_ram_limit(45)
    logger.info(f"stage {args.stage} args {vars(args)}")
    if args.stage in ("select", "judge", "analyze"):
        from src import analysis
        getattr(analysis, f"stage_{args.stage}")(args)
        return
    globals()[f"stage_{args.stage}"](args)


if __name__ == "__main__":
    logger.catch(main, reraise=True)()
