#!/usr/bin/env python3
"""Freeze pre-registered predictions BEFORE any confirmation sample exists.

  freeze.py c1   -> results/frozen_c1_temperature.json (from results/temperature_law_screen.json)
  freeze.py c4v0 -> results/frozen_c4_reference_v0.json (from results/c4_reference.json, screen grid only)
  freeze.py c4   -> results/frozen_c4_reference.json
  (C3 is frozen by s6_seed_readout.py, which builds its own body.)

Each file = {body, sha256 = sha256(canonical JSON of body, sort_keys), frozen_utc}. verify() recomputes the hash;
generation scripts call verify() and refuse to run on a missing or tampered file. Every freeze is appended to
logs/freeze_log.jsonl (append-only; this workspace is not a git repository, so this log replaces a git commit).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LABELS_PATH, LOGS, RESULTS, canonical_sha, load_json, read_jsonl, save_json  # noqa: E402


def write_frozen(path: Path, body: dict) -> str:
    sha = canonical_sha(body)
    save_json(path, dict(body=body, sha256=sha, frozen_utc=dt.datetime.now(dt.timezone.utc).isoformat()))
    with (LOGS / "freeze_log.jsonl").open("a") as fh:
        fh.write(json.dumps(dict(file=path.name, sha256=sha, utc=dt.datetime.now(dt.timezone.utc).isoformat()))
                 + "\n")
    print(f"FROZEN {path.name} sha256={sha}")
    return sha


def verify(path: Path) -> dict:
    """Return the frozen dict or exit non-zero if missing / tampered."""
    if not path.exists():
        print(f"REFUSING: frozen file {path.name} does not exist", file=sys.stderr)
        sys.exit(3)
    d = json.loads(path.read_text())
    sha = canonical_sha(d.get("body"))
    if sha != d.get("sha256"):
        print(f"REFUSING: {path.name} hash mismatch (stored {d.get('sha256')}, recomputed {sha})", file=sys.stderr)
        sys.exit(4)
    print(f"verified {path.name} sha256={sha}")
    return d


def freeze_c1() -> str:
    scr = load_json(RESULTS / "temperature_law_screen.json")
    lab = read_jsonl(LABELS_PATH)
    p1 = {t: dict(Counter(r["label"] for r in lab if r["source"] == "ban" and r["task"] == t
                          and r["cond"] == "baseline")) for t in ("T1", "T2", "T3")}
    lines = {}
    for key, ar in scr["arrhenius"].items():
        if "error" in ar or not ar["eligible"]:
            continue
        lines[key] = dict(reference=ar["reference"], eligible=ar["eligible"],
                          lines={j: {k: ar["lines"][j][k] for k in ("a", "b", "a_se", "b_se", "r2", "underpowered")}
                                 for j in ar["lines"]},
                          glm=scr["glm"].get(key), top3_T1=scr["reversals"][key]["top3_T1"],
                          reversal_verdicts=scr["c1_criteria"][key], hill=scr["hill"].get(key))
    body = dict(claim="C1 temperature law (Arrhenius / multinomial-logit) frozen on the iteration-1 grid screen",
                thresholds=dict(r2_min=0.85, alpha_beta_slope_ratio_min=3.0, reversal_T_max=1.3),
                anchoring_rule=("re-draw prediction: P_T(j) prop. exp(a*_j + b_j/T) over {mode, eligible, pooled rest};"
                                " b_j frozen; a*_j = ln(s_j/s_mode) - b_j/0.7 with s = P1 screen baseline counts+0.5"
                                " (ban-arm baseline n=300, top-k none) so that the T=0.7 prediction equals it"),
                baselines=["fixed-utility logit p_T prop. s^(0.7/T) (intercept 0)", "no temperature effect p_T = s"],
                lines=lines, p1_baseline_counts=p1, screen_sha=canonical_sha(scr))
    return write_frozen(RESULTS / "frozen_c1_temperature.json", body)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "c1"
    if what == "c1":
        freeze_c1()
    elif what in ("c4v0", "c4"):
        src = load_json(RESULTS / "c4_reference.json")
        write_frozen(RESULTS / ("frozen_c4_reference_v0.json" if what == "c4v0" else "frozen_c4_reference.json"),
                     src)
    elif what == "verify":
        verify(Path(sys.argv[2]))
    else:
        raise SystemExit(f"unknown target {what}")
