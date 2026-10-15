"""select / judge / analyze stages: metrics with bootstrap CIs, survival rules, judge, figures, method_out.json."""

from __future__ import annotations

import asyncio
import json
import math
import os
import random
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from loguru import logger

from protocol.prompts import DISPLAY_NAME, TASKS, TAXONOMY, build_user_prompt
from src.acts_io import load_acts
from src.common import GENS, JUDGE, RES, ROOT, SCORED, append_jsonl, read_jsonl

NONIDEA = {"no_code", "syntax_error"}
OUTSIDE = {"other", "random_walk"}
B_BOOT = 2000
RNG = np.random.default_rng(0)
JUDGE_MODEL = "openai/gpt-4.1-mini"
JUDGE_CAP = 1.5
N_MAIN = 150  # sweep indices 0..149 (baseline restricted to the same seeds for like-for-like rows)


def ctx() -> dict:
    return json.loads((RES / "context.json").read_text())


# ------------------------------------------------------------------------------------------- loading
def load_task(task: str) -> dict[str, list[dict]]:
    """setting -> scored records (dedup by idx, last wins), sorted by idx."""
    out = {}
    for p in sorted((SCORED / task).glob("*.jsonl")):
        recs = {}
        for r in read_jsonl(p):
            recs[r["idx"]] = r
        out[p.stem] = [recs[k] for k in sorted(recs)]
    return out


def judge_map() -> dict:
    return {r["key"]: r for r in read_jsonl(JUDGE / "verdicts.jsonl") if r.get("verdict")}


# ------------------------------------------------------------------------------------------- metrics
def ent_bits(labels: list[str]) -> float:
    c = Counter(l for l in labels if l not in NONIDEA)
    n = sum(c.values())
    return -sum(v / n * math.log2(v / n) for v in c.values()) if n else 0.0


def metric_fns(task_menu: list[str], p0: dict, jm: dict, task: str):
    def outside_novel(r):
        if not (r["pass"] and r["label"] in OUTSIDE):
            return 0.0
        v = jm.get(f"{task}:{r['code_hash']}")
        return 1.0 if v and v["verdict"] == "distinct_novel" else 0.0

    def outside_rule(r):
        return 1.0 if (r["pass"] and r["label"] in OUTSIDE) else 0.0

    def offmenu(r):
        return 1.0 if (r["pass"] and r["label"] not in set(task_menu) | NONIDEA) else 0.0

    def atyp(r):
        return -math.log(p0[r["label"]]) if r["label"] in p0 else float("nan")

    def degen(r):
        return 1.0 if (r["deg_no_code"] or r["deg_syntax_error"] or r["deg_truncated"] or r["deg_looping"]
                       or r["deg_missing_function"]) else 0.0

    per_sample = {"pass": lambda r: float(r["pass"]), "frac_correct": lambda r: r["frac_correct"],
                  "outside_menu_correct_share": outside_novel, "outside_menu_rule_share": outside_rule,
                  "offmenu_correct_share": offmenu, "atypicality": atyp, "degeneration": degen,
                  "no_code": lambda r: float(r["deg_no_code"]), "truncated": lambda r: float(r["deg_truncated"]),
                  "looping": lambda r: float(r["deg_looping"])}
    return per_sample


def set_metrics(recs: list[dict], fns: dict) -> dict:
    labs = [r["label"] for r in recs]
    out = {k: float(np.nanmean([f(r) for r in recs])) if recs else float("nan") for k, f in fns.items()}
    c = Counter(l for l in labs if l not in NONIDEA)
    n = sum(c.values())
    H = ent_bits(labs)
    K = len(c)
    out["entropy"] = H
    out["entropy_mm"] = H + ((K - 1) / (2 * n * math.log(2)) if n else 0.0)
    out["entropy_pass"] = ent_bits([r["label"] for r in recs if r["pass"]])
    out["hill0"] = float(K)
    out["hill1"] = float(2 ** H)
    out["hill2"] = float(1.0 / sum((v / n) ** 2 for v in c.values())) if n else 0.0
    out["n"] = len(recs)
    out["label_counts"] = dict(Counter(labs).most_common())
    return out


def boot_ci(recs: list[dict], fn, B: int = B_BOOT) -> list[float]:
    if not recs:
        return [float("nan")] * 2
    n = len(recs)
    vals = []
    for _ in range(B):
        ix = RNG.integers(0, n, n)
        vals.append(fn([recs[i] for i in ix]))
    return [float(np.nanpercentile(vals, 2.5)), float(np.nanpercentile(vals, 97.5))]


def boot_diff(a: list[dict], b: list[dict], fn, B: int = B_BOOT) -> dict:
    """CI of fn(a)-fn(b). Paired by idx where indices coincide, else independent resampling."""
    ia = {r["idx"]: r for r in a}
    ib = {r["idx"]: r for r in b}
    common = sorted(set(ia) & set(ib))
    paired = len(common) == len(a) == len(b)
    vals = []
    for _ in range(B):
        if paired:
            ix = RNG.integers(0, len(common), len(common))
            ra = [ia[common[i]] for i in ix]
            rb = [ib[common[i]] for i in ix]
        else:
            ra = [a[i] for i in RNG.integers(0, len(a), len(a))]
            rb = [b[i] for i in RNG.integers(0, len(b), len(b))]
        vals.append(fn(ra) - fn(rb))
    d = fn(a) - fn(b)
    lo, hi = float(np.nanpercentile(vals, 2.5)), float(np.nanpercentile(vals, 97.5))
    return {"diff": float(d), "ci": [lo, hi], "excludes_0": bool(lo > 0 or hi < 0), "paired": paired}


def ent_fn(recs):
    return ent_bits([r["label"] for r in recs])


def mean_fn(f):
    return lambda recs: float(np.nanmean([f(r) for r in recs])) if recs else float("nan")


def p0_for(base: list[dict]) -> dict:
    c = Counter(r["label"] for r in base if r["label"] not in NONIDEA)
    n = sum(c.values())
    return {k: (c.get(k, 0) + 0.5) / (n + 0.5 * len(TAXONOMY)) for k in TAXONOMY}


def pooled_boot_diff(recsA: dict, recsB: dict, fn, B: int = B_BOOT) -> dict:
    """Pooled = mean over tasks of per-task metric; bootstrap resamples within task."""
    vals = []
    tasks = [t for t in ("T1", "T3") if recsA.get(t) and recsB.get(t)]
    if not tasks:
        return {"diff": float("nan"), "ci": [float("nan")] * 2, "excludes_0": False}
    for _ in range(B):
        dd = []
        for t in tasks:
            a, b = recsA[t], recsB[t]
            ra = [a[i] for i in RNG.integers(0, len(a), len(a))]
            rb = [b[i] for i in RNG.integers(0, len(b), len(b))]
            dd.append(fn(ra, t) - fn(rb, t))
        vals.append(np.mean(dd))
    d = float(np.mean([fn(recsA[t], t) - fn(recsB[t], t) for t in tasks]))
    lo, hi = float(np.nanpercentile(vals, 2.5)), float(np.nanpercentile(vals, 97.5))
    return {"diff": d, "ci": [lo, hi], "excludes_0": bool(lo > 0 or hi < 0)}


# ------------------------------------------------------------------------------------------- table
def build_table(include_ho: bool = True) -> dict:
    C = ctx()
    jm = judge_map()
    table = {}
    settings_meta = {}
    for p in [RES / "sweep_settings.json", RES / "heldout_settings.json", RES / "explore_settings.json"]:
        if p.exists():
            for d in json.loads(p.read_text()):
                settings_meta[d["name"]] = d
    data = {t: load_task(t) for t in ("T1", "T3")}
    for t in ("T1", "T3"):
        menu = C["menus"][t]["classes"]
        p0 = p0_for(data[t]["baseline"])
        fns = metric_fns(menu, p0, jm, t)
        base_lab = {r["idx"]: r["label"] for r in data[t]["baseline"]}
        for name, recs in data[t].items():
            if name.endswith("__ho") and not include_ho:
                continue
            recs_eval = [r for r in recs if r["idx"] < N_MAIN] if name == "baseline" else recs
            m = set_metrics(recs_eval, fns)
            shared = [r for r in recs if r["idx"] in base_lab and name != "baseline"]
            m["flip_rate_vs_baseline"] = float(np.mean([r["label"] != base_lab[r["idx"]] for r in shared])) \
                if shared else None
            meta = settings_meta.get(name, {})
            fam = meta.get("family") or ("baseline" if name == "baseline" else "calib" if name.startswith("calib")
                                         else "gts" if name == "gts" else "unknown")
            table.setdefault(name, {"family": fam, "params": meta.get("params", {}), "iv": meta.get("iv", {}),
                                    "tasks": {}})["tasks"][t] = m
    base_pass = {t: table["baseline"]["tasks"][t]["pass"] for t in ("T1", "T3")}
    # baseline uses all 300 for the eligibility reference
    for t in ("T1", "T3"):
        base_pass[t] = float(np.mean([r["pass"] for r in data[t]["baseline"]]))
    for name, row in table.items():
        tk = row["tasks"]
        if all(t in tk for t in ("T1", "T3")):
            row["pooled"] = {k: float(np.mean([tk["T1"][k], tk["T3"][k]])) for k in tk["T1"]
                             if isinstance(tk["T1"][k], (int, float)) and tk["T1"][k] is not None
                             and tk["T3"].get(k) is not None}
            row["eligible_pooled"] = bool(row["pooled"]["pass"] >= 0.8 * np.mean(list(base_pass.values())))
        row["eligible"] = {t: bool(tk[t]["pass"] >= 0.8 * base_pass[t]) for t in tk}
    return {"table": table, "base_pass": base_pass, "data": data}


# ------------------------------------------------------------------------------------------- select
def _best(table: dict, fam: str, key: str, tiebreak: tuple = ("offmenu_correct_share", "entropy")):
    cands = [(n, r) for n, r in table.items() if r["family"] == fam and r.get("eligible_pooled")
             and not n.endswith("__ho")]
    if not cands:
        return None
    return max(cands, key=lambda x: tuple([x[1]["pooled"].get(key, -1)] + [x[1]["pooled"].get(k, -1) for k in tiebreak]))[0]


def stage_select(args) -> None:
    T = build_table(include_ho=False)
    table = T["table"]
    sw = json.loads((RES / "sweep_settings.json").read_text())
    # temperature family includes the T=0.7 baseline as a candidate
    temps = [n for n, r in table.items() if r["family"] == "temperature" and r.get("eligible_pooled")]
    temps_all = temps + ["baseline"]
    best_temp = max(temps_all, key=lambda n: table[n]["pooled"]["entropy"])
    picks = {"temperature": best_temp}
    for fam in ("H-probe", "H-dim"):
        picks[fam] = _best(table, fam, "entropy", ("pass",))
    for fam in ("A3-proj", "A3-leace"):
        picks[fam] = _best(table, fam, "outside_menu_correct_share")
    plan = []

    def add(name, d):
        d = dict(d)
        d["name"] = name + "__ho"
        d.pop("indices", None)
        plan.append(d)

    base_d = {"name": "temp0.7", "family": "temperature", "task": "T1", "cond": "plain", "T": 0.7, "topk": 0,
              "iv": {}, "code_stop": True, "params": {"T": 0.7}}
    for t in ("T1", "T3"):
        add("temp0.7", {**base_d, "task": t})
        if best_temp != "baseline":
            add(best_temp, {**sw_lookup(sw, best_temp, t)})
        for c in ("prompt_new", "prompt_novel2000", "prompt_ban3"):
            add(c, sw_lookup(sw, c, t))
        for fam in ("H-probe", "H-dim"):
            n = picks.get(fam)
            if n:
                d = sw_lookup(sw, n, t)
                add(n, d)
                a = d["iv"]["alpha"]
                add(f"Radd_a{a:.3g}_d0", {**d, "name": "", "family": "R-add",
                                           "iv": {"kind": "add", "vec": "rand0", "alpha": a},
                                           "params": {"alpha": a, "draw": 0}})
        for fam in ("A3-proj", "A3-leace"):
            n = picks.get(fam)
            if n:
                d = sw_lookup(sw, n, t)
                add(n, d)
                k = ctx()["k"][t]
                r = d["iv"].get("r", max(1, k - 1))
                a = d["iv"]["a"]
                add(f"Rproj_r{r}_a{a:.3g}_d0", {**d, "family": "R-proj",
                                                 "iv": {"kind": "project", "basis": "rand0", "r": r, "a": a},
                                                 "params": {"r": r, "a": a, "draw": 0}})
    # dedupe
    seen, uniq = set(), []
    for d in plan:
        key = (d["name"], d["task"])
        if key not in seen:
            seen.add(key)
            uniq.append(d)
    out = {"picks": picks, "settings": uniq,
           "note": "best-of-method on indices 0..99 among eligible settings (pass >= 0.8 x baseline, pooled); "
                   "held-out fresh seeds 1000..1099"}
    (RES / "heldout_plan.json").write_text(json.dumps(out, indent=2))
    (RES / "heldout_settings.json").write_text(json.dumps(uniq, indent=1))
    logger.info(f"picks: {picks}; {len(uniq)} held-out settings")


def sw_lookup(sw: list, name: str, task: str) -> dict:
    for d in sw:
        if d["name"] == name and d["task"] == task:
            return dict(d)
    # names are shared across tasks; sweep_settings.json keeps both tasks -> scan list
    raise KeyError(f"{name}/{task}")


# ------------------------------------------------------------------------------------------- judge
JUDGE_FAMILIES = [c for c in TAXONOMY if c != "other"] + ["other_known", "distinct_novel"]
JUDGE_PROMPT = """You are an expert in graph algorithms auditing generated code. Task given to the code author:
---
{task}
---
Code (comments and docstrings removed):
```python
{code}
```
Classify the core search ALGORITHM this code implements into exactly one family:
- floyd_warshall, bellman_ford, spfa (queue-based Bellman-Ford with re-enqueue), bidirectional (two frontiers),
  astar (priority g+h with heuristic), greedy_best_first (priority = heuristic only), dijkstra (priority queue /
  min-selection keyed by accumulated distance, incl. uniform-cost search), dial_bucket, iddfs, bfs (FIFO frontier),
  dfs (stack or recursion), random_walk
- other_known: a known algorithm or a trivial variant/renaming/reordering of one that is not in the list above
- distinct_novel: a genuinely different search algorithm that is NOT a renamed, reordered or trivially modified
  known algorithm
Answer with JSON only: {{"family": "<one family name>", "justification": "<one sentence>"}}"""


async def _judge_all(items: list[dict], budget: float) -> None:
    from openai import AsyncOpenAI, PermissionDeniedError, APIStatusError
    client = AsyncOpenAI(base_url=os.environ["OPENROUTER_BASE_URL"], api_key=os.environ["OPENROUTER_API_KEY"])
    sem = asyncio.Semaphore(8)
    state = {"cost": float((JUDGE / "cost.json").exists() and json.loads((JUDGE / "cost.json").read_text())["cost"]),
             "stop": False, "n": 0}

    async def one(it):
        async with sem:
            if state["stop"] or state["cost"] >= budget:
                return
            for attempt in range(3):
                try:
                    resp = await client.chat.completions.create(
                        model=JUDGE_MODEL, temperature=0, max_tokens=200,
                        response_format={"type": "json_object"},
                        messages=[{"role": "user", "content": it["prompt"]}], extra_body={"usage": {"include": True}})
                    break
                except PermissionDeniedError as e:
                    if "AI Inventor per-run OpenRouter budget" in str(e):
                        logger.error("OpenRouter budget refusal -> stopping judge batch")
                        state["stop"] = True
                        return
                    raise
                except APIStatusError as e:
                    if "AI Inventor per-run OpenRouter budget" in str(e):
                        state["stop"] = True
                        return
                    if attempt == 2:
                        logger.warning(f"judge failed {it['key']}: {e}")
                        return
                    await asyncio.sleep(2 + attempt * 3)
                except Exception as e:  # network / parse errors: retry then skip
                    if attempt == 2:
                        logger.warning(f"judge error {it['key']}: {type(e).__name__} {e}")
                        return
                    await asyncio.sleep(2)
            if state["stop"]:
                return
            cost = 0.0
            u = getattr(resp, "usage", None)
            if u is not None:
                cost = float(getattr(u, "cost", None) or (u.model_extra or {}).get("cost", 0.0) or 0.0)
            state["cost"] += cost
            state["n"] += 1
            txt = resp.choices[0].message.content or ""
            try:
                js = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
                fam = str(js.get("family", "")).strip()
            except (json.JSONDecodeError, ValueError):
                js, fam = {}, ""
            if fam not in JUDGE_FAMILIES:
                fam = "unparsed"
            rec = {"key": it["key"], "verdict": fam, "justification": str(js.get("justification", ""))[:400],
                   "cost": cost, "model": JUDGE_MODEL, "sets": it["sets"]}
            append_jsonl(JUDGE / "verdicts.jsonl", [rec])
            logger.debug(f"judge {it['key']} -> {fam} (${cost:.5f}) {rec['justification'][:120]}")
            if state["n"] % 50 == 0:
                logger.info(f"judge progress {state['n']} calls, cost ${state['cost']:.4f}")

    await asyncio.gather(*[one(it) for it in items], return_exceptions=False)
    (JUDGE / "cost.json").write_text(json.dumps({"cost": state["cost"], "model": JUDGE_MODEL, "cap": budget,
                                                 "stopped_on_refusal": state["stop"]}))
    logger.info(f"judge done: {state['n']} calls, total cost ${state['cost']:.4f}")


def stage_judge(args) -> None:
    import requests
    r = requests.get(os.environ["OPENROUTER_BASE_URL"].rstrip("/") + "/key",
                     headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}, timeout=30)
    logger.info(f"OpenRouter key status: {r.text[:300]}")
    done = judge_map()
    data = {t: load_task(t) for t in ("T1", "T3")}
    items, keys = [], set()
    # Set A: every passing program the rule labels other/random_walk
    for t, sets in data.items():
        for name, recs in sets.items():
            for rr in recs:
                if rr["pass"] and rr["label"] in OUTSIDE and rr["code_hash"]:
                    k = f"{t}:{rr['code_hash']}"
                    if k not in done and k not in keys:
                        keys.add(k)
                        items.append({"key": k, "sets": ["A"], "prompt": JUDGE_PROMPT.format(
                            task=build_user_prompt(t), code=rr["stripped"][:5000])})
    # Set B: stratified audit sample (~15 per rule class, all conditions)
    audit_p = JUDGE / "audit_sample.json"
    if audit_p.exists():
        audit = json.loads(audit_p.read_text())
    else:
        pool = defaultdict(list)
        for t, sets in data.items():
            for name, recs in sets.items():
                for rr in recs:
                    if rr["code_hash"] and rr["label"] not in NONIDEA:
                        pool[rr["label"]].append((t, name, rr["idx"], rr["code_hash"], rr["label"]))
        rng = random.Random(0)
        audit, per = [], max(15, 200 // max(1, len(pool)))
        seen = set()
        for lab in sorted(pool):
            cand = [c for c in pool[lab]]
            rng.shuffle(cand)
            got = 0
            for c in cand:
                if (c[0], c[3]) in seen:
                    continue
                seen.add((c[0], c[3]))
                audit.append(c)
                got += 1
                if got >= per:
                    break
        # top up to 200 from the largest classes
        rest = [c for lab in sorted(pool, key=lambda l: -len(pool[l])) for c in pool[lab] if (c[0], c[3]) not in seen]
        rng.shuffle(rest)
        for c in rest:
            if len(audit) >= 200:
                break
            if (c[0], c[3]) not in seen:
                seen.add((c[0], c[3]))
                audit.append(c)
        audit = audit[:200]
        audit_p.write_text(json.dumps(audit))
    strip_by = {}
    for t, sets in data.items():
        for name, recs in sets.items():
            for rr in recs:
                if rr["code_hash"]:
                    strip_by[(t, rr["code_hash"])] = rr["stripped"]
    for (t, name, idx, h, lab) in audit:
        k = f"{t}:{h}"
        if k not in done and k not in keys:
            keys.add(k)
            items.append({"key": k, "sets": ["B"], "prompt": JUDGE_PROMPT.format(task=build_user_prompt(t),
                                                                                   code=strip_by[(t, h)][:5000])})
    est = len(items) * (1100 * 0.4 + 70 * 1.6) / 1e6
    logger.info(f"judge: {len(items)} new calls (estimated ${est:.3f}); cap ${JUDGE_CAP}")
    if items:
        asyncio.run(_judge_all(items, JUDGE_CAP))


# ------------------------------------------------------------------------------------------- analyze helpers
def load_caps(task: str, setting: str) -> dict:
    d = ROOT / "caps" / task / setting
    out = {}
    if not d.exists():
        return out
    parts = [np.load(p) for p in sorted(d.glob("*.npz"))]
    if not parts:
        return out
    keys = [k for k in parts[0].files]
    for k in keys:
        out[k] = np.concatenate([p[k] for p in parts])
    return out


def fit_capture_probes(C: dict) -> dict:
    """Probes trained on baseline mean(gen1..32) at band layers and band_max+2 (pooled tasks)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    classes = C["probe_classes"]
    layers = C["band"] + [max(C["band"]) + 2]
    acts = {t: load_acts(ROOT / "acts", t) for t in ("T1", "T3")}
    labs = []
    for t in ("T1", "T3"):
        lab = {r["idx"]: r["label"] for r in read_jsonl(SCORED / t / "baseline.jsonl")}
        idx = np.load(ROOT / "acts" / f"baseline_{t}_idx.npy")
        labs += [lab[int(i)] if lab[int(i)] in classes else "rare" for i in idx]
    out = {}
    for l in layers:
        X = np.concatenate([acts[t][:, 9, l, :].astype(np.float32) for t in ("T1", "T3")])
        sc = StandardScaler().fit(X)
        clf = LogisticRegression(C=float(C["probe_C"][str(l)]), max_iter=500).fit(sc.transform(X), labs)
        out[l] = (sc, clf)
    return out


def manipulation_checks(C: dict, table: dict) -> dict:
    from sklearn.metrics import balanced_accuracy_score
    probes = fit_capture_probes(C)
    band = C["band"]
    mid = band[1]
    down = max(band) + 2
    res = {"probe_layers": {"band_mid": mid, "downstream": down},
           "note": "probes trained on baseline mean(gen1..32) residuals; applied to residuals captured DURING steered "
                   "generation (post-intervention, mean gen1..32). menu_entropy = entropy (bits) of probe softmax "
                   "restricted to the task menu; decod_bal_acc = balanced accuracy of the baseline probe predicting "
                   "the realized idea label of the steered sample.", "settings": {}}
    for t in ("T1", "T3"):
        menu = C["menus"][t]["classes"]
        data = load_task(t)
        for name, row in table.items():
            if row["family"] not in ("H-probe", "H-dim", "A3-proj", "A3-leace", "A4", "R-add", "R-proj", "crn",
                                     "temperature", "prompt"):
                continue
            cap = load_caps(t, name)
            if not cap:
                continue
            labs_by = {r["idx"]: r["label"] for r in data.get(name, [])}
            idx = cap["idx"]
            y = [labs_by.get(int(i), "missing") for i in idx]
            y = [c if c in C["probe_classes"] else "rare" for c in y]
            entry = {}
            for tag, l in (("band_mid", mid), ("downstream", down)):
                key = f"m32_{l}"
                if key not in cap:
                    continue
                sc, clf = probes[l]
                P = clf.predict_proba(sc.transform(cap[key].astype(np.float32)))
                cls = list(clf.classes_)
                mi = [cls.index(c) for c in menu if c in cls]
                pm = P[:, mi] / np.clip(P[:, mi].sum(1, keepdims=True), 1e-12, None)
                ent = float(np.mean(-(pm * np.log2(np.clip(pm, 1e-12, None))).sum(1)))
                pred = clf.predict(sc.transform(cap[key].astype(np.float32)))
                ok = [i for i, c in enumerate(y) if c != "missing"]
                bal = float(balanced_accuracy_score([y[i] for i in ok], [pred[i] for i in ok])) if len(
                    set(y[i] for i in ok)) > 1 else None
                entry[tag] = {"menu_entropy_bits": ent, "decod_bal_acc": bal, "n": len(ok)}
            res["settings"].setdefault(name, {})[t] = entry
    return res


def classifier_audit(data: dict) -> dict:
    jm = judge_map()
    audit_p = JUDGE / "audit_sample.json"
    if not audit_p.exists():
        return {"status": "not run"}
    audit = json.loads(audit_p.read_text())
    pairs = []
    for (t, name, idx, h, lab) in audit:
        v = jm.get(f"{t}:{h}")
        if v:
            j = v["verdict"]
            j = "other" if j in ("other_known", "distinct_novel", "unparsed") else j
            pairs.append((lab, j))
    if not pairs:
        return {"status": "no verdicts"}
    labs = sorted(set(a for a, _ in pairs) | set(b for _, b in pairs))
    M = {a: {b: 0 for b in labs} for a in labs}
    for a, b in pairs:
        M[a][b] += 1
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    pa = Counter(a for a, _ in pairs)
    pb = Counter(b for _, b in pairs)
    pe = sum(pa[c] * pb[c] for c in labs) / n ** 2
    kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0
    return {"n": n, "agreement": po, "cohen_kappa": kappa, "matrix_rule_rows_judge_cols": M,
            "kappa_below_0.6": kappa < 0.6}


def commitment_analysis() -> dict:
    """Token index of the first explicit algorithm-name mention in baseline generations."""
    import re as _re
    from transformers import AutoTokenizer
    from protocol.prompts import MODEL_ID
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    pat = _re.compile(r"breadth|depth|bfs|dfs|dijkstra|a\*|a-star|bellman|floyd|bidirectional|greedy|"
                      r"heuristic|iterative deepening|uniform", _re.I)
    out = {}
    for t in ("T1", "T3"):
        pos = []
        for r in read_jsonl(GENS / t / "baseline.jsonl"):
            m = pat.search(r["text"])
            pos.append(len(tok(r["text"][:m.start()], add_special_tokens=False)["input_ids"]) + 1 if m else None)
        valid = [p for p in pos if p is not None]
        out[t] = {"n": len(pos), "mentions": len(valid), "median_token": float(np.median(valid)) if valid else None,
                  "share_within_8": float(np.mean([p <= 8 for p in valid])) if valid else None,
                  "share_within_32": float(np.mean([p <= 32 for p in valid])) if valid else None,
                  "share_within_64": float(np.mean([p <= 64 for p in valid])) if valid else None,
                  "quartiles": [float(x) for x in np.percentile(valid, [25, 50, 75])] if valid else None}
    return out


# ------------------------------------------------------------------------------------------- survival
def _get(data, t, name):
    return data[t].get(name, [])


def survival(T: dict, C: dict) -> dict:
    from scipy.stats import spearmanr
    table, data = T["table"], T["data"]
    plan = json.loads((RES / "heldout_plan.json").read_text()) if (RES / "heldout_plan.json").exists() else None
    if plan is not None and not any(n.endswith("__ho") for n in table):
        plan = None  # held-out draw not generated (yet)
    out = {"heldout_available": plan is not None}
    jm = judge_map()
    fnsets = {t: metric_fns(C["menus"][t]["classes"], p0_for(data[t]["baseline"]), jm, t) for t in ("T1", "T3")}
    if plan:
        picks = plan["picks"]
        ho = lambda n: n + "__ho"  # noqa: E731
        temp_cands = [ho("temp0.7")] + ([ho(picks["temperature"])] if picks["temperature"] != "baseline" else [])
        temp_cands = [n for n in temp_cands if n in table]
        best_t = max(temp_cands, key=lambda n: table[n]["pooled"]["entropy"])
        out["heldout_best_temperature"] = best_t
        for fam in ("H-probe", "H-dim"):
            n = picks.get(fam)
            if not n or ho(n) not in table:
                out[fam] = {"survives": False, "reason": "no eligible setting at matched pass rate"}
                continue
            a = table[ho(n)]["params"].get("alpha")
            ctrl = ho(f"Radd_a{a:.3g}_d0")
            r = {"setting": n, "alpha": a, "control": ctrl}
            for t in ("T1", "T3"):
                hH = table[ho(n)]["tasks"][t]["entropy"]
                hT = table[best_t]["tasks"][t]["entropy"]
                r[t] = {"entropy_H": hH, "entropy_best_temp": hT, "ratio": hH / hT if hT > 0 else float("inf"),
                        "ratio_ge_2": hH >= 2 * hT,
                        "vs_control": boot_diff(_get(data, t, ho(n)), _get(data, t, ctrl), ent_fn),
                        "pass_H": table[ho(n)]["tasks"][t]["pass"],
                        "eligible_on_heldout": table[ho(n)]["eligible"][t]}
            hHp, hTp = table[ho(n)]["pooled"]["entropy"], table[best_t]["pooled"]["entropy"]
            pooled_ctrl = pooled_boot_diff({t: _get(data, t, ho(n)) for t in ("T1", "T3")},
                                           {t: _get(data, t, ctrl) for t in ("T1", "T3")}, lambda rr, t: ent_fn(rr))
            r["pooled"] = {"entropy_H": hHp, "entropy_best_temp": hTp, "ratio_ge_2": hHp >= 2 * hTp,
                           "vs_control": pooled_ctrl}
            r["survives"] = bool(r["T1"]["ratio_ge_2"] and r["T1"]["vs_control"]["diff"] > 0 and
                                 r["T1"]["vs_control"]["excludes_0"] and r["pooled"]["ratio_ge_2"] and
                                 pooled_ctrl["diff"] > 0 and pooled_ctrl["excludes_0"])
            out[fam] = r
        comps = [n for n in temp_cands + [ho("prompt_new"), ho("prompt_novel2000"), ho("prompt_ban3")] if n in table]
        for fam in ("A3-proj", "A3-leace"):
            n = picks.get(fam)
            if not n or ho(n) not in table:
                out[fam] = {"survives": False, "reason": "no eligible setting at matched pass rate"}
                continue
            prm = table[ho(n)]["iv"]
            r_ = prm.get("r", 1)
            ctrl = ho(f"Rproj_r{r_}_a{prm['a']:.3g}_d0")
            key = "outside_menu_correct_share"
            s_a3 = table[ho(n)]["pooled"][key]
            comp_vals = {c: table[c]["pooled"][key] for c in comps}
            mx = max(comp_vals.values()) if comp_vals else 0.0
            f = lambda rr, t: mean_fn(fnsets[t][key])(rr)  # noqa: E731
            pc = pooled_boot_diff({t: _get(data, t, ho(n)) for t in ("T1", "T3")},
                                  {t: _get(data, t, ctrl) for t in ("T1", "T3")}, f) if ctrl in table else None
            r = {"setting": n, "control": ctrl, "share_A3_pooled": s_a3, "comparators": comp_vals, "max_comparator": mx,
                 "ratio_ge_3": s_a3 >= 3 * mx, "abs_ge_0.05": s_a3 >= 0.05, "vs_control": pc,
                 "rule_only_upper_bound_A3": table[ho(n)]["pooled"]["outside_menu_rule_share"],
                 "offmenu_correct_share_A3": table[ho(n)]["pooled"]["offmenu_correct_share"],
                 "pass_A3": table[ho(n)]["pooled"]["pass"]}
            r["survives"] = bool(r["ratio_ge_3"] and r["abs_ge_0.05"] and pc is not None and pc["diff"] > 0 and
                                 pc["excludes_0"])
            out[fam] = r
    # A4 (no selection -> evaluated on sweep indices directly)
    alphas = sorted(C["alphas"].get("A4", []))
    a4 = {"alphas": [0.0] + alphas, "tasks": {}}
    ok_all = True
    for t in ("T1", "T3"):
        fa = fnsets[t]["atypicality"]
        base = [r for r in data[t]["baseline"] if r["idx"] < N_MAIN]
        doses = [base] + [_get(data, t, f"A4_a{a:.3g}") for a in alphas]
        aty = [float(np.nanmean([fa(r) for r in d])) if d else float("nan") for d in doses]
        rho = float(spearmanr([0.0] + alphas, aty).correlation)
        boots = []
        for _ in range(1000):
            bv = [float(np.nanmean([fa(d[i]) for i in RNG.integers(0, len(d), len(d))])) for d in doses]
            boots.append(spearmanr([0.0] + alphas, bv).correlation)
        top = doses[-1]
        rand_top = [r for d in range(3) for r in _get(data, t, f"Radd_a{alphas[-1]:.3g}_d{d}")]
        vs = boot_diff(top, rand_top, mean_fn(fa)) if rand_top else None
        # proportionality: delta log p_j vs -log p0_j at the top strength
        p0 = p0_for(data[t]["baseline"])
        ct = Counter(r["label"] for r in top if r["label"] not in NONIDEA)
        nt = sum(ct.values())
        pt = {k: (ct.get(k, 0) + 0.5) / (nt + 0.5 * len(TAXONOMY)) for k in TAXONOMY}
        xs = np.array([-math.log(p0[k]) for k in TAXONOMY])
        ys = np.array([math.log(pt[k]) - math.log(p0[k]) for k in TAXONOMY])
        slope = float(np.polyfit(xs, ys, 1)[0])
        a4["tasks"][t] = {"atypicality": aty, "spearman": rho, "spearman_ci": [float(np.nanpercentile(boots, 2.5)),
                                                                               float(np.nanpercentile(boots, 97.5))],
                          "pass": [float(np.mean([r["pass"] for r in d])) if d else None for d in doses],
                          "top_vs_radd": vs, "slope_dlogp_vs_neglogp0": slope}
        ok_all &= bool(rho >= 0.8 and vs is not None and vs["diff"] > 0 and vs["excludes_0"])
    a4["survives"] = bool(ok_all)
    out["A4"] = a4
    surv = [k for k in ("H-probe", "H-dim", "A3-proj", "A3-leace", "A4") if out.get(k, {}).get("survives")]
    out["survivors"] = surv
    return out


def pareto(points: list[tuple[str, float, float]]) -> list[str]:
    front = []
    for n, x, y in points:
        if not any((x2 >= x and y2 >= y and (x2 > x or y2 > y)) for n2, x2, y2 in points if n2 != n):
            front.append(n)
    return front


# ------------------------------------------------------------------------------------------- phrasing diversity
def phrasing_diversity(recs: list[dict], cap: int = 25) -> float | None:
    import Levenshtein
    c = Counter(r["label"] for r in recs if r["label"] not in NONIDEA)
    if not c:
        return None
    mode = c.most_common(1)[0][0]
    codes = [r["stripped"] for r in recs if r["label"] == mode and r["stripped"]][:cap]
    if len(codes) < 2:
        return None
    ds = []
    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            ds.append(Levenshtein.distance(codes[i], codes[j]) / max(len(codes[i]), len(codes[j]), 1))
    return float(np.mean(ds))


# ------------------------------------------------------------------------------------------- figures
CONTROL_FAMS = {"R-add", "R-proj", "crn"}
FAM_COLORS = {"baseline": "#000000", "temperature": "#1f77b4", "prompt": "#ff7f0e", "gts": "#8c564b",
              "H-probe": "#2ca02c", "H-dim": "#98df8a", "H-probe-explore": "#bcbd22", "H-dim-explore": "#dbdb8d", "A3-proj": "#d62728", "A3-leace": "#ff9896", "A4": "#9467bd",
              "R-add": "#bbbbbb", "R-proj": "#888888", "crn": "#17becf"}


def make_figures(T: dict, C: dict, surv: dict, out_dir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 9, "pdf.fonttype": 42, "axes.spines.top": False, "axes.spines.right": False})
    files = []
    table, data = T["table"], T["data"]
    main = {n: r for n, r in table.items() if not n.endswith("__ho") and r["family"] != "calib" and "pooled" in r}

    def save(fig, name):
        for ext in ("png", "pdf"):
            fig.savefig(out_dir / f"{name}.{ext}", dpi=200, bbox_inches="tight")
        plt.close(fig)
        files.append(f"figs/{name}.png")

    # 1 probe curve
    pc = json.loads((RES / "probe_curve.json").read_text())
    L = [r["layer"] for r in pc["layers"]]
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.plot(L, [r["bal_acc_pooled"] for r in pc["layers"]], "-o", ms=3, label="probe, mean(gen1..32)")
    ax.plot(L, [r["shuf_bal_acc_pooled"] for r in pc["layers"]], "--", label="within-task shuffled labels")
    ax.plot(L, [r["per_position_bal_acc"]["mean_gen1_8"] for r in pc["layers"]], ":", label="mean(gen1..8)")
    for k in (1, 8):
        ax.plot(L, [r["per_position_bal_acc"][f"gen{k}"] for r in pc["layers"]], lw=0.8, alpha=0.6, label=f"gen{k} only")
    ax.axvspan(min(pc["band"]) - 0.5, max(pc["band"]) + 0.5, color="orange", alpha=0.2, label="steering band")
    ax.set_xlabel("hidden-state layer")
    ax.set_ylabel("balanced accuracy (5-fold)")
    ax.set_title("Idea probes (T1+T3 pooled; classes: " + ", ".join(pc["classes"]) + ")")
    ax.legend(fontsize=7, ncol=2)
    save(fig, "fig_probe_curve")

    # 2/3 Pareto fronts
    for key, lab, fname in (("entropy", "idea entropy (bits, pooled T1/T3)", "fig_pareto_entropy"),
                            ("offmenu_correct_share", "off-menu & correct share (pooled)", "fig_pareto_offmenu"),
                            ("outside_menu_correct_share", "judge-confirmed novel & correct share", "fig_pareto_outside")):
        fig, ax = plt.subplots(figsize=(6.4, 4.2))
        pts = [(n, r["pooled"]["pass"], r["pooled"][key]) for n, r in main.items()]
        front = set(pareto([p for p in pts if main[p[0]]["family"] not in CONTROL_FAMS]))
        for fam in FAM_COLORS:
            xs = [(p, v, n) for n, p, v in pts if main[n]["family"] == fam]
            if xs:
                ax.scatter([x[0] for x in xs], [x[1] for x in xs], s=18, c=FAM_COLORS[fam], label=fam, alpha=0.85)
        fp = sorted([(p, v, n) for n, p, v in pts if n in front])
        ax.plot([x[0] for x in fp], [x[1] for x in fp], "k--", lw=0.8)
        for p, v, n in fp:
            ax.annotate(n, (p, v), fontsize=6, xytext=(3, 2), textcoords="offset points")
        ax.axvline(0.8 * np.mean(list(T["base_pass"].values())), color="red", lw=0.8, ls=":",
                   label="eligibility (0.8 x baseline pass)")
        ax.set_title("dashed = Pareto front over methods (random controls shown in grey, excluded from front)", fontsize=7)
        ax.set_xlabel("oracle pass rate (pooled T1/T3)")
        ax.set_ylabel(lab)
        ax.legend(fontsize=6, ncol=2)
        save(fig, fname)

    # 4 violin of frac_correct per family-best
    reps = ["baseline", surv_pick(T, "temperature"), "prompt_new", "prompt_novel2000", "prompt_ban3", "gts"] + \
        [surv_pick(T, f) for f in ("H-probe", "H-dim", "A3-proj", "A3-leace")] + \
        ([f"A4_a{max(C['alphas']['A4']):.3g}"] if C.get("alphas", {}).get("A4") else [])
    reps = [r for r in dict.fromkeys(reps) if r and r in table]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), sharey=True)
    for ax, t in zip(axes, ("T1", "T3")):
        vals = [[r["frac_correct"] for r in (data[t].get(n) or [])] or [0] for n in reps]
        ax.violinplot(vals, showmedians=True)
        ax.set_xticks(range(1, len(reps) + 1))
        ax.set_xticklabels(reps, rotation=60, ha="right", fontsize=6)
        ax.set_title(f"{t}: per-sample fraction of 50 graphs correct")
    save(fig, "fig_violin_frac_correct")

    # 5 A4 dose response
    a4 = surv.get("A4")
    if a4:
        fig, ax = plt.subplots(figsize=(5, 3.2))
        for t, m in a4["tasks"].items():
            ax.plot(a4["alphas"], m["atypicality"], "-o", label=f"{t} A4 (rho={m['spearman']:.2f})")
        ax.set_xlabel("alpha (x median residual norm)")
        ax.set_ylabel("atypicality: mean -log p0(label)")
        ax.legend(fontsize=7)
        save(fig, "fig_a4_dose")

    # 6 idea share bars
    show = reps + [n for n in ("temp1.0", "temp1.3", "temp1.6", "temp2.0", "temp1.6_top10") if n in table]
    show = list(dict.fromkeys(show))
    fig, axes = plt.subplots(2, 1, figsize=(9, 6))
    for ax, t in zip(axes, ("T1", "T3")):
        labs = [l for l in TAXONOMY + ["no_code", "syntax_error"]]
        bottom = np.zeros(len(show))
        cmap = plt.get_cmap("tab20")
        for li, l in enumerate(labs):
            v = np.array([table[n]["tasks"][t]["label_counts"].get(l, 0) / max(1, table[n]["tasks"][t]["n"])
                          if t in table[n]["tasks"] else 0 for n in show])
            if v.sum() > 0:
                ax.bar(range(len(show)), v, bottom=bottom, color=cmap(li), label=l)
                bottom += v
        ax.set_xticks(range(len(show)))
        ax.set_xticklabels(show, rotation=50, ha="right", fontsize=6)
        ax.set_ylabel(f"{t} idea share")
    axes[0].legend(fontsize=6, ncol=5, loc="upper right")
    save(fig, "fig_idea_shares")

    # 7 PCA manifold view at band-middle layer (mean gen1..32): baseline vs ban3 vs best A3
    try:
        l = C["band"][1]
        fig, axes = plt.subplots(1, 2, figsize=(10, 4.4))
        for ax, t in zip(axes, ("T1", "T3")):
            acts = load_acts(ROOT / "acts", t)[:, 9, l, :].astype(np.float32)
            idx = np.load(ROOT / "acts" / f"baseline_{t}_idx.npy")
            lab = {r["idx"]: r["label"] for r in data[t]["baseline"]}
            mu = acts.mean(0)
            _, _, Vt = np.linalg.svd(acts - mu, full_matrices=False)
            Pc = Vt[:2].T
            groups = [("baseline", acts, [lab[int(i)] for i in idx], "o")]
            for nm, mk in (("prompt_ban3", "s"), (surv_pick(T, "A3-proj"), "^")):
                if not nm:
                    continue
                cap = load_caps(t, nm)
                if cap and f"m32_{l}" in cap:
                    lb = {r["idx"]: r["label"] for r in data[t].get(nm, [])}
                    groups.append((nm, cap[f"m32_{l}"].astype(np.float32), [lb.get(int(i), "?") for i in cap["idx"]], mk))
            cols = {c: plt.get_cmap("tab20")(i) for i, c in enumerate(TAXONOMY + ["no_code", "syntax_error", "?"])}
            for gname, X, labs, mk in groups:
                Z = (X - mu) @ Pc
                ax.scatter(Z[:, 0], Z[:, 1], s=4, alpha=0.15, marker=mk, c=[cols.get(c, "k") for c in labs])
                cnt = Counter(labs)
                for c, n in cnt.items():
                    m = np.array([x == c for x in labs])
                    cz = Z[m].mean(0)
                    ax.scatter(cz[0], cz[1], s=20 + 400 * n / len(labs), marker=mk, c=[cols.get(c, "k")],
                               edgecolors="k", linewidths=0.6)
                    if n / len(labs) > 0.04:
                        ax.annotate(f"{gname[:10]}:{c}", cz, fontsize=6)
            ax.set_title(f"{t}: PCA, mean(gen1..32), layer {l}\no=baseline  s=ban3  ^=best A3-proj", fontsize=8)
        save(fig, "fig_pca_manifold")
    except (FileNotFoundError, KeyError, ValueError) as e:
        logger.warning(f"PCA figure skipped: {e}")
    return files


def surv_pick(T: dict, fam: str) -> str | None:
    p = RES / "heldout_plan.json"
    if p.exists():
        return json.loads(p.read_text())["picks"].get(fam)
    return None


# ------------------------------------------------------------------------------------------- analyze
def add_cis(T: dict, C: dict) -> None:
    """Bootstrap CIs (per task) for pass, entropy, off-menu/outside shares, atypicality; + phrasing diversity."""
    jm = judge_map()
    data = T["data"]
    for t in ("T1", "T3"):
        fns = metric_fns(C["menus"][t]["classes"], p0_for(data[t]["baseline"]), jm, t)
        for name, row in T["table"].items():
            if t not in row["tasks"] or row["family"] == "calib":
                continue
            recs = data[t][name]
            if name == "baseline":
                recs = [r for r in recs if r["idx"] < N_MAIN]
            m = row["tasks"][t]
            m["ci"] = {"pass": boot_ci(recs, mean_fn(fns["pass"]), 1000),
                       "entropy": boot_ci(recs, ent_fn, 1000),
                       "offmenu_correct_share": boot_ci(recs, mean_fn(fns["offmenu_correct_share"]), 1000),
                       "outside_menu_correct_share": boot_ci(recs, mean_fn(fns["outside_menu_correct_share"]), 1000)}
            m["phrasing_diversity_modal_idea"] = phrasing_diversity(recs)


def controls_vs_knobs(T: dict) -> dict:
    """Every additive knob setting vs pooled R-add draws at the same alpha (entropy, flip rate)."""
    out = {}
    data, table = T["data"], T["table"]
    for name, row in table.items():
        if row["family"] not in ("H-probe", "H-dim", "A4") or name.endswith("__ho"):
            continue
        a = row["params"].get("alpha")
        rnames = [f"Radd_a{a:.3g}_d{d}" for d in range(3)]
        for t in ("T1", "T3"):
            rr = [r for n in rnames for r in data[t].get(n, [])]
            if not rr:
                continue
            out.setdefault(name, {})[t] = {"entropy_vs_radd": boot_diff(data[t][name], rr, ent_fn, 1000),
                                           "pass_vs_radd": boot_diff(data[t][name], rr,
                                                                     mean_fn(lambda r: float(r["pass"])), 1000)}
    return out


def gts_stats() -> dict:
    out = {}
    for t in ("T1", "T3"):
        g = read_jsonl(GENS / t / "gts.jsonl")
        if not g:
            out[t] = "not run"
            continue
        items = Counter((r.get("gts_item") or "<parse failed>").split(":")[0].split(" - ")[0].strip()[:60] for r in g)
        out[t] = {"n": len(g), "parse_failed": sum(1 for r in g if not r.get("gts_item")),
                  "mean_items_listed": float(np.mean([r.get("gts_n_items", 0) for r in g])),
                  "top_picked_items": items.most_common(15)}
    return out


def stage_analyze(args) -> None:
    C = ctx()
    T = build_table(include_ho=True)
    logger.info(f"table: {len(T['table'])} settings")
    add_cis(T, C)
    surv = survival(T, C)
    logger.info(f"survivors: {surv['survivors']}")
    manip = manipulation_checks(C, T["table"])
    audit = classifier_audit(T["data"])
    commit = commitment_analysis()
    ctrl = controls_vs_knobs(T)
    figs = make_figures(T, C, surv, ROOT / "figs")
    # Pareto rankings
    table = T["table"]
    main = {n: r for n, r in table.items() if not n.endswith("__ho") and r["family"] != "calib" and "pooled" in r}
    fronts = {}
    for key in ("entropy", "offmenu_correct_share", "outside_menu_correct_share", "entropy_pass"):
        pts = [(n, r["pooled"]["pass"], r["pooled"][key]) for n, r in main.items()]
        front = pareto([p for p in pts if main[p[0]]["family"] not in CONTROL_FAMS])
        front_with_controls = pareto(pts)
        elig = [(n, r["pooled"][key]) for n, r in main.items() if r.get("eligible_pooled")]
        elig.sort(key=lambda x: -x[1])
        prompt_like = [x for x in elig if main[x[0]]["family"] in ("prompt", "gts", "temperature", "baseline")]
        internal = [x for x in elig if main[x[0]]["family"] in ("H-probe", "H-dim", "A3-proj", "A3-leace", "A4")]
        fronts[key] = {"pareto_front": [{"setting": n, "family": main[n]["family"], "pass": main[n]["pooled"]["pass"],
                                         key: main[n]["pooled"][key]} for n in front],
                       "controls_on_front_if_included": [n for n in front_with_controls
                                                          if main[n]["family"] in CONTROL_FAMS],
                       "eligible_ranking_top10": [{"setting": n, "family": main[n]["family"], key: v} for n, v in elig[:10]],
                       "best_prompt_or_temperature": prompt_like[0] if prompt_like else None,
                       "best_internal_knob": internal[0] if internal else None}
    headline = ("internal knob(s) survive: " + ", ".join(surv["survivors"])) if surv["survivors"] else (
        "prompting ceiling: no internal knob survives the pre-registered rules; top of fronts -> " +
        "; ".join(f"{k}: {v['best_prompt_or_temperature'][0] if v['best_prompt_or_temperature'] else 'n/a'}"
                  for k, v in fronts.items()))
    judge_cost = json.loads((JUDGE / "cost.json").read_text()) if (JUDGE / "cost.json").exists() else {"status": "not run"}
    slim_table = {n: {k: v for k, v in r.items()} for n, r in table.items()}
    results = {
        "headline": headline, "survival": surv, "pareto": fronts, "manipulation_checks": manip,
        "classifier_audit": audit, "commitment_point": commit, "knob_vs_random_controls": ctrl,
        "gen_then_select": gts_stats(), "judge_cost": judge_cost, "base_pass": T["base_pass"],
        "settings": slim_table, "figures": figs,
        "context": {k: C[k] for k in ("menus", "k", "ban3", "ban3_text", "band", "median_norm", "alphas", "probe_classes")
                    if k in C},
        "probe_curve": json.loads((RES / "probe_curve.json").read_text()),
        "calibration": json.loads((RES / "calibration.json").read_text()),
        "rules": json.loads((RES / "rules.json").read_text()),
        "vector_checks": json.loads((RES / "vector_checks.json").read_text()),
        "heldout_plan": json.loads((RES / "heldout_plan.json").read_text()) if (RES / "heldout_plan.json").exists() else "not run",
    }
    (RES / "results.json").write_text(json.dumps(results, indent=1, default=str))
    write_method_out(T, results, C)
    logger.info(f"HEADLINE: {headline}")


def write_method_out(T: dict, results: dict, C: dict) -> None:
    data, table = T["data"], T["table"]
    picks = results["heldout_plan"]["picks"] if isinstance(results["heldout_plan"], dict) else {}
    a4top = f"A4_a{max(C['alphas']['A4']):.3g}" if C.get("alphas", {}).get("A4") else None
    show = {"temperature_best": picks.get("temperature"), "temp2p0": "temp2.0", "prompt_new": "prompt_new",
            "prompt_novel2000": "prompt_novel2000", "prompt_ban3": "prompt_ban3", "gen_then_select": "gts",
            "H_probe_best": picks.get("H-probe"), "H_dim_best": picks.get("H-dim"), "A3_proj_best": picks.get("A3-proj"),
            "A3_leace_best": picks.get("A3-leace"), "A4_top": a4top}
    gens = {t: {} for t in ("T1", "T3")}
    for t in ("T1", "T3"):
        for key, nm in list(show.items()) + [("baseline", "baseline")]:
            if nm and nm != "baseline" or key == "baseline":
                gens[t][key] = {r["idx"]: r for r in read_jsonl(GENS / t / f"{nm}.jsonl")}
    datasets = []
    for t, dname in (("T1", "T1_open_path_search"), ("T3", "T3_weighted_shortest_path")):
        sc_by = {n: {r["idx"]: r for r in recs} for n, recs in data[t].items()}
        exs = []
        for i in range(N_MAIN):
            b = gens[t]["baseline"].get(i)
            if b is None:
                continue
            ex = {"input": build_user_prompt(t), "output": b["text"][:4000],
                  "metadata_task": t, "metadata_seed_index": i,
                  "metadata_per_setting": {n: {"label": s[i]["label"], "pass": s[i]["pass"],
                                               "frac_correct": round(s[i]["frac_correct"], 3)}
                                           for n, s in sc_by.items() if i in s and not n.startswith("calib")}}
            ex["predict_baseline_T07"] = b["text"][:4000]
            for key, nm in show.items():
                g = gens[t].get(key, {}).get(i)
                if g is not None:
                    ex[f"predict_{key}"] = g["text"][:4000]
            exs.append(ex)
        datasets.append({"dataset": dname, "examples": exs})
    meta = {"method_name": "Influence arm: internal knobs (H-flatten, A3 menu erasure, A4 unusualness dial) vs "
                           "temperature/prompting for novel-but-correct code",
            "model": "Qwen/Qwen2.5-3B-Instruct", "show_settings": show,
            **{k: v for k, v in results.items() if k not in ("settings",)},
            "settings_metrics": {n: {kk: vv for kk, vv in r.items()} for n, r in results["settings"].items()}}
    out = {"metadata": meta, "datasets": datasets}
    (ROOT / "method_out.json").write_text(json.dumps(out, default=str))
    logger.info("method_out.json written")
