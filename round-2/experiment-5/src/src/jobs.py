#!/usr/bin/env python3
"""Write job specs for each generation stage (data/conf/jobs_<stage>.json)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from protocol import ROOT, bannable  # noqa: E402

CONF = ROOT / "data" / "conf"
T3_FORCED = ["Dijkstra", "A_star", "Bellman_Ford", "Floyd_Warshall", "Bidirectional", "BFS"]


def job(task, cond, seeds, banned=None, sub="gen"):
    return dict(task=task, condition=cond, banned=banned or [], seeds=list(seeds),
                out=f"data/conf/{sub}/{task}/{cond}.jsonl")


def stage_forced() -> list[dict]:
    js = []
    for t in ("T1", "T2"):
        js += [job(t, f"forced_{c}", range(1000, 1030)) for c in bannable(t)]
    js += [job("T3", f"forced_{c}", range(1000, 1030)) for c in T3_FORCED]
    return js


def screen_pairs() -> dict:
    """6 random unordered pairs per task (T1, T2) from bannable classes seen in any screen label file."""
    import itertools
    import numpy as np
    from protocol import taxonomy
    path = CONF / "pairs.json"
    if path.exists():
        return json.loads(path.read_text())
    plan = json.loads((ROOT / "data" / "ban_plan.json").read_text())
    rng = np.random.default_rng(20261016)
    out = {}
    for t in ("T1", "T2"):
        seen = set()
        for p in (ROOT / "data" / "labels" / t).glob("*.jsonl"):
            seen |= {json.loads(x)["label"] for x in p.read_text().splitlines() if x.strip()}
        cls = [c for c in bannable(t) if c in seen]
        screen_sets = {frozenset(v) for v in plan[t].values() if v}
        combos = [list(c) for c in itertools.combinations(cls, 2) if frozenset(c) not in screen_sets]
        pick = rng.choice(len(combos), size=6, replace=False)
        out[t] = [sorted(combos[i], key=taxonomy(t).index) for i in pick]
    path.write_text(json.dumps(out, indent=1))
    return out


CONF_SINGLES = {"T1": ["Greedy_best_first", "Bidirectional", "IDDFS", "Bellman_Ford"],
                "T2": ["Heap", "Counting", "Radix", "Shell"], "T3": ["SPFA", "BFS"]}
MENTIONS = {"T1": ["BFS", "A_star"], "T2": ["Bubble", "Merge"]}
PLACEBO_BLOCKS = {"placebo_b1": range(1000, 1100), "placebo_b2": range(2000, 2100), "placebo_b3": range(3000, 3100)}
N100 = range(1000, 1100)


def stage_conf_nonban() -> list[dict]:
    js = []
    for t in ("T1", "T2", "T3", "T4"):
        js += [job(t, b, s) for b, s in PLACEBO_BLOCKS.items()]
    for t in ("T1", "T2"):
        js += [job(t, "alt_placebo", N100)] + [job(t, f"mention_{c}", N100) for c in MENTIONS[t]]
    from protocol_ext import bannable as bann_ext
    js += [job("T4", "baseline", range(1000, 1300)), job("T4", "comention", range(1000, 1050))]
    js += [job("T4", f"forced_{c}", range(1000, 1040)) for c in bann_ext("T4")]
    return js


def stage_conf_bans() -> list[dict]:
    pairs = screen_pairs()
    js = []
    for t, cs in CONF_SINGLES.items():
        js += [job(t, f"ban_{c}", N100, [c]) for c in cs]
    for t, ps in pairs.items():
        js += [job(t, f"pair_{a}__{b}", N100, [a, b]) for a, b in ps]
    js += [job(t, "cross", N100) for t in ("T1", "T2")]
    return js


def stage_t4_bans() -> list[dict]:
    plan = json.loads((CONF / "T4_plan.json").read_text())
    return [job("T4", c, N100, b) for c, b in plan["conditions"].items()]


if __name__ == "__main__":
    stage = sys.argv[1]
    CONF.mkdir(parents=True, exist_ok=True)
    js = {"forced": stage_forced, "conf_nonban": stage_conf_nonban, "conf_bans": stage_conf_bans,
          "t4_bans": stage_t4_bans}[stage]()
    (CONF / f"jobs_{stage}.json").write_text(json.dumps(js, indent=1))
    print(stage, len(js), sum(len(j["seeds"]) for j in js))
