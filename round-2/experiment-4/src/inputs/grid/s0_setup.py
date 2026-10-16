#!/usr/bin/env python3
"""S0: render prompts, draw seed strings, freeze the pre-registration (sha256 + git commit)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
import subprocess

from loguru import logger

from common import CONFIG, MODEL, PROMPTS, ROOT, TASKS, TEMPS, TOPKS, save_json, setup_logging

NOUNS = """apple anchor arrow axe bag ball balloon banana barn basket bat bath beach bean bear bed bee bell belt bench
bicycle bird blanket boat bone book boot bottle bowl box bread brick bridge broom brush bucket bus butter button cabin
cake camel camera candle cannon cap car carpet carrot castle cat chain chair chalk cheese cherry chess chicken chimney
church circle clock cloud coat coin comb compass cookie cord corn couch cow crab crown cup curtain desk diamond dog doll
door dragon drum duck eagle egg elephant engine envelope eye fan feather fence finger fire fish flag flower flute fork
fox frog garden gate ghost gift glass glove goat gold grape grass guitar hammer hand hat heart helmet hill honey hook
horn horse house ice island jacket jar jeep jewel kettle key kite knife ladder lamp leaf lemon letter lion lock map
marble mask match mirror monkey moon mountain mouse mug nail needle nest net nose notebook nut oar ocean onion orange
owl oven paint palm pan paper parrot peach pear pearl pen pencil penguin piano pig pillow pin pipe plane plate pocket
pond pot potato pumpkin puzzle rabbit radio rain rake ring river road robot rock roof rope rose sail salt sand saw scarf
school scissors seed sheep shell ship shirt shoe shovel sink skate skirt sled snake snow soap sock sofa spoon square
stair star stone stove straw street sugar sun swan sword table tail tea teapot tent tiger toast tooth torch towel tower
toy tractor train tree truck tulip turtle umbrella valley vase violin wagon wall watch whale wheel whistle window wing
wire wolf wood worm yacht zebra bread cliff canyon desert forest meadow lantern feather pebble saddle barrel cradle
glacier harbor lagoon orchard prism quilt rocket satchel thimble trumpet volcano walnut""".split()
NOUNS = list(dict.fromkeys(NOUNS))

PREREG = {
    "study": "Temperature arm: does temperature change ideas or just wording? (Qwen2.5-3B-Instruct)",
    "primary_sample": "n=100 per cell (sample_idx 0..99, seed = sample_idx), top_k = none (-1) for Arrhenius/reversals",
    "temperatures": TEMPS,
    "topk": TOPKS,
    "H_SURVIVES": "C1 & C2 & C3",
    "C1": ">=75% of the 90 forked samples have t* <= 47 (TV<=0.125 to final label for all t'>=t*) AND are single-dominant "
          "(k_BIC<=1 or largest single segment jump >= 0.6 x total rise y_0->y_47)",
    "C2": "median Arrhenius R^2 >= 0.85 over eligible ideas (all tasks pooled) AND zero SIGNIFICANT top-3 rank reversals at T<=1.3 "
          "(bootstrap 95% CI of share difference excludes 0 in flipped direction, 2000 resamples)",
    "C3": "slope-gap Spearman >= 0.6 on >= 2 of 3 tasks; tasks with <3 eligible non-mode ideas are 'not evaluable'; "
          "if <2 tasks evaluable, pooled Spearman >= 0.6 is used and the substitution reported",
    "A1_SURVIVES": "(A: delta-AIC > 4 favouring QUAD for >= half of eligible ideas OR B: >=1 significant top-3 reversal at T<=1.6) "
                   "AND C: path-multiplicity Spearman >= 0.6 (pooled)",
    "VERDICT": "'H' if H only, 'A1' if A1 only, 'ambiguous' otherwise; every sub-criterion reported with value/threshold/pass",
    "definitions": {
        "mode": "most frequent idea at T=0.3 (ties broken at T=0.5), top_k=none",
        "eligible": "share >= 3% at T=1.0 (top_k=none), excluding 'other' and the mode",
        "arrhenius": "binary logit of j vs mode over 6 temperatures: LIN log-odds = c - s/T vs QUAD + q/T^2; ML on raw counts; "
                     "delta-AIC = AIC_lin - AIC_quad; R^2 from WLS on +0.5-smoothed empirical log-odds, weights 1/var",
        "gap": "median over forked base paths of u_mode - u_j at t*, u_j = max log p(w) over idea-j tokens (T=1 logits); "
               "missing -> log p of the 20th token (upper bound on u_j)",
        "path_multiplicity": "M_j = mean over base paths with final label != j of #{t in 1..47: share_j(o_t) >= 1/8}",
        "A1_C_target": "share_j(T=1.6) - share_j(T=0.7), ideas with share >= 3% at either T, pooled over tasks",
        "commitment": "t* = smallest t with TV(o_t', onehot(final)) <= 0.125 for all t' in [t,47]; 8 rollouts, T=0.7, 320 tokens",
    },
    "secondary_not_in_verdict": [
        "beta of slope ~ gap regression (H predicts ~1)", "steepness ratio d log alpha_1/dT / d log beta_1/dT >= 3",
        "top-k=10 ceiling violations = 0", "seed |pred-obs| <= 0.10; seeds <5% flips where gap/sigma > 3",
        "n=300 replication of C2/C3 (if run)", "probe-vs-control margin"],
    "reserved_never_touch": ["google/gemma-2-2b-it", "selection / k-th smallest tasks"],
}


def char_seed(rng: random.Random) -> str:
    return "".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(11))


def main() -> None:
    setup_logging("s0_setup")
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    prompts = {}
    for t in TASKS:
        s = tok.apply_chat_template([{"role": "user", "content": PROMPTS[t]}], add_generation_prompt=True, tokenize=False)
        ids = tok(s, add_special_tokens=False)["input_ids"]
        prompts[t] = {"user": PROMPTS[t], "rendered": s, "ids": ids}
        logger.info(f"{t}: {len(ids)} prompt tokens\n{s}")
    save_json(CONFIG / "prompts.json", prompts)
    r1, r2 = random.Random(20260101), random.Random(20260102)
    seeds = [{"idx": i, "kind": "char", "string": f"seed={char_seed(r1)}"} for i in range(30)]
    seeds += [{"idx": 30 + i, "kind": "word", "string": "seed=(" + " ".join(r2.sample(NOUNS, 4)) + ")"} for i in range(30)]
    seeded = {}
    for t in TASKS:
        seeded[t] = []
        for sd in seeds:
            content = sd["string"] + "\n\n" + PROMPTS[t]
            s = tok.apply_chat_template([{"role": "user", "content": content}], add_generation_prompt=True, tokenize=False)
            seeded[t].append({**sd, "rendered": s, "ids": tok(s, add_special_tokens=False)["input_ids"]})
    save_json(CONFIG / "seeds.json", {"seeds": seeds, "prompts": seeded, "n_nouns": len(NOUNS)})
    logger.info(f"seeds: {seeds[0]['string']} | {seeds[30]['string']} | nouns={len(NOUNS)}")
    pre = CONFIG / "preregistration.json"
    if pre.exists():
        logger.warning("preregistration.json exists; NOT overwriting (frozen)")
    else:
        PREREG["frozen_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        pre.write_text(json.dumps(PREREG, indent=1, sort_keys=True))
    sha = hashlib.sha256(pre.read_bytes()).hexdigest()
    subprocess.run(["git", "init", "-q"], cwd=ROOT, check=False)
    subprocess.run(["git", "add", "config/preregistration.json"], cwd=ROOT, check=True)
    subprocess.run(["git", "-c", "user.name=AMGrobelnik", "-c", "user.email=noreply@ai-inventor", "commit", "-q", "-m",
                    "Freeze pre-registration before any data is generated\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"],
                   cwd=ROOT, check=False)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    save_json(CONFIG / "prereg_lock.json", {"sha256": sha, "git_commit": commit,
                                            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat()})
    logger.info(f"preregistration sha256={sha} commit={commit}")


if __name__ == "__main__":
    main()
