"""Tabulate the ban arm's (gen_art_experiment_2) labelled generations, which the iteration-1 report omits."""
import json, math, collections, sys
from pathlib import Path
L = Path(sys.argv[1]) / "data" / "labels"
def ent(c):
    c = {k: v for k, v in c.items() if k != "Unparseable"}; n = sum(c.values())
    return -sum(v/n*math.log2(v/n) for v in c.values()) if n else 0.0
out = {}
for t in ["T1", "T2", "T3"]:
    for f in sorted((L / t).glob("*.jsonl")):
        rows = [json.loads(l) for l in open(f)]
        c = collections.Counter(r["label"] for r in rows); banned = rows[0].get("banned") or []
        out[f"{t}/{f.stem}"] = dict(n=len(rows), entropy=round(ent(c), 3), still_banned=sum(c[b] for b in banned),
                                    banned=banned, labels=dict(c.most_common()))
for k, v in out.items(): print(k, v)
json.dump(out, open("recompute_ban_arm_out.json", "w"), indent=1)
