"""Independent recomputation of headline numbers in the iteration-1 report from the influence arm's scored files."""
import json, math, collections, sys
from pathlib import Path
C = Path(sys.argv[1])
NON = {"syntax_error", "no_code", "unparseable", "missing", "none"}
def load(t, s):
    p = C / "scored" / t / f"{s}.jsonl"
    return [json.loads(l) for l in open(p)] if p.exists() else None
def ent(labels):
    c = collections.Counter(l for l in labels if l not in NON and not str(l).startswith("deg"))
    n = sum(c.values()); return -sum(v/n*math.log2(v/n) for v in c.values()) if n else 0.0
def summ(t, s, lo=0, hi=10**9):
    r = load(t, s)
    if r is None: return None
    r = [x for x in r if lo <= x["idx"] < hi]
    labs = [x["label"] for x in r]
    return dict(n=len(r), pass_=round(sum(bool(x["pass"]) for x in r)/len(r), 3), H=round(ent(labs), 3),
                labels=dict(collections.Counter(labs).most_common()))
out = {}
for s, rng in [("baseline", (0, 300)), ("baseline", (0, 150)), ("crn_rerun", (0, 150)), ("temp1.0", (0, 150)),
               ("prompt_ban3", (0, 150)), ("prompt_new", (0, 150)), ("prompt_novel2000", (0, 150)), ("gts", (0, 150)),
               ("Hdim_a0.224", (0, 150)), ("A4_a0.356", (0, 150)), ("Radd_a1.12_d2", (0, 75)),
               ("temp0.7__ho", (0, 10**9)), ("Hdim_a0.05__ho", (0, 10**9)), ("prompt_ban3__ho", (0, 10**9))]:
    for t in ["T1", "T3"]:
        out[f"{s}[{rng[0]}:{rng[1]}] {t}"] = summ(t, s, *rng)
for k, v in out.items(): print(k, v)
# ban compliance (influence arm)
for t, banned in [("T1", {"bfs", "dfs", "dijkstra"}), ("T3", {"dijkstra", "bfs", "spfa"})]:
    r = [x for x in load(t, "prompt_ban3") if x["idx"] < 150]
    print("ban3 still-banned", t, sum(x["label"] in banned for x in r), "/", len(r))
# held-out entropy ratios
for t in ["T1", "T3"]:
    a = summ(t, "Hdim_a0.05__ho"); b = summ(t, "temp0.7__ho")
    print("heldout ratio", t, round(a["H"]/b["H"], 3))
json.dump(out, open("recompute_out.json", "w"), indent=1)
