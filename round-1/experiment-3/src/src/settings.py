"""Setting registry: every condition (baselines, practitioner knobs, internal knobs, controls) as data."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class Setting:
    name: str
    family: str  # baseline | temperature | prompt | gts | H-probe | H-dim | A3-proj | A3-leace | A4 | R-add | R-proj | crn
    task: str
    cond: str = "plain"  # plain|new|novel2000|ban3|gts_list|gts
    T: float = 0.7
    topk: int = 0
    iv: dict = field(default_factory=dict)  # intervention spec ({} = none)
    indices: list = field(default_factory=list)
    code_stop: bool = True
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def fmt(x: float) -> str:
    return f"{x:.3g}"


def build_main_settings(cfg: dict, task: str, n_main: int = 100, n_ctrl: int = 50) -> list[Setting]:
    """Full sweep for one task. cfg: calibration alphas per knob, A3 menu size k, etc."""
    main = list(range(n_main))
    ctrl = list(range(n_ctrl))
    S: list[Setting] = []
    # practitioner baselines
    for T in (1.0, 1.3, 1.6, 2.0):
        S.append(Setting(f"temp{T}", "temperature", task, T=T, indices=main, params={"T": T}))
    S.append(Setting("temp1.6_top10", "temperature", task, T=1.6, topk=10, indices=main, params={"T": 1.6, "topk": 10}))
    for c in ("new", "novel2000", "ban3"):
        S.append(Setting(f"prompt_{c}", "prompt", task, cond=c, indices=main, params={"cond": c}))
    S.append(Setting("crn_rerun", "crn", task, indices=main, params={"note": "plain T=0.7 re-generated in mixed batches"}))
    # H-flatten
    for knob, fam in (("Hprobe", "H-probe"), ("Hdim", "H-dim"), ("A4", "A4")):
        if not cfg["alphas"].get(knob):
            continue
        for a in cfg["alphas"][knob]:
            S.append(Setting(f"{knob}_a{fmt(a)}", fam, task, iv={"kind": "add", "vec": knob, "alpha": a},
                             indices=main, params={"alpha": a}))
        for a in sorted(cfg["alphas"][knob])[-3:]:
            for d in range(3):
                S.append(Setting(f"Radd_a{fmt(a)}_d{d}", "R-add", task, iv={"kind": "add", "vec": f"rand{d}", "alpha": a},
                                 indices=ctrl, params={"alpha": a, "draw": d}))
    # A3 erasure
    k = cfg["k"][task]
    if k >= 2:
        for r in range(1, k):
            S.append(Setting(f"A3proj_r{r}_a1", "A3-proj", task, iv={"kind": "project", "basis": "A3", "r": r, "a": 1.0},
                             indices=main, params={"r": r, "a": 1.0}))
        for a in (0.25, 0.5, 0.75):
            S.append(Setting(f"A3proj_r{k - 1}_a{fmt(a)}", "A3-proj", task,
                             iv={"kind": "project", "basis": "A3", "r": k - 1, "a": a}, indices=main,
                             params={"r": k - 1, "a": a}))
        for a in (0.5, 1.0):
            S.append(Setting(f"A3leace_a{fmt(a)}", "A3-leace", task, iv={"kind": "leace", "a": a}, indices=main,
                             params={"a": a}))
        for (r, a) in sorted({(1, 1.0), (k - 1, 1.0), (k - 1, 0.5)}):
            for d in range(3):
                S.append(Setting(f"Rproj_r{r}_a{fmt(a)}_d{d}", "R-proj", task,
                                 iv={"kind": "project", "basis": f"rand{d}", "r": r, "a": a}, indices=ctrl,
                                 params={"r": r, "a": a, "draw": d}))
    # dedupe by name (R-add may repeat across knobs with equal alpha)
    seen, out = set(), []
    for s in S:
        if s.name not in seen:
            seen.add(s.name)
            out.append(s)
    return out


def gts_settings(task: str, indices: list[int]) -> list[Setting]:
    return [Setting("gts_list", "gts", task, cond="gts_list", indices=indices, code_stop=False),
            Setting("gts", "gts", task, cond="gts", indices=indices)]


def spec_key(task: str, iv: dict) -> str:
    return task + "|" + json.dumps(iv, sort_keys=True)
