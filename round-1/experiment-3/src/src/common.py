"""Paths, hardware limits, jsonl I/O, scoring (classifier + oracle) with a code-hash cache."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import resource
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from protocol.classifier import classify_text  # noqa: E402
from protocol.oracle import Oracle, run_one  # noqa: E402
from protocol.prompts import TASKS  # noqa: E402

GENS = ROOT / "gens"
CAPS = ROOT / "caps"
SCORED = ROOT / "scored"
VEC = ROOT / "vectors"
ACTS = ROOT / "acts"
RES = ROOT / "results"
FIGS = ROOT / "figs"
JUDGE = ROOT / "judge"
for d in (GENS, CAPS, SCORED, VEC, ACTS, RES, FIGS, JUDGE, ROOT / "logs"):
    d.mkdir(exist_ok=True)


def setup_logging(name: str) -> None:
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
    logger.add(str(ROOT / "logs" / f"{name}.log"), rotation="30 MB", level="DEBUG")


def container_ram_gb() -> float:
    for p in ["/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"]:
        try:
            v = Path(p).read_text().strip()
            if v != "max" and int(v) < 1_000_000_000_000:
                return int(v) / 1e9
        except (FileNotFoundError, ValueError):
            pass
    return 57.0


def set_ram_limit(gb: float) -> None:
    lim = int(gb * 1e9)
    resource.setrlimit(resource.RLIMIT_AS, (lim, lim))


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning(f"bad jsonl line in {p}")
    return out


def append_jsonl(p: Path, recs: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")


def degeneration_flags(text: str, ntoks: int, hit_max: bool, cls: dict, func: str) -> dict:
    code = cls.get("code")
    toks = text.split()
    looping = False
    if len(toks) >= 40:
        grams = Counter(tuple(toks[i:i + 20]) for i in range(0, len(toks) - 19))
        looping = grams.most_common(1)[0][1] >= 4
    return {
        "no_code": code is None,
        "syntax_error": cls["label"] == "syntax_error",
        "truncated": bool(hit_max) and not re.search(r"```[ \t]*(?:python|py|Python|python3)[ \t]*\n.*?```", text, re.S),
        "looping": looping,
        "missing_function": code is not None and not re.search(rf"def\s+{func}\s*\(", code),
    }


class Scorer:
    """Classify + oracle every generation; cache oracle results by (task, code hash)."""

    def __init__(self, n_threads: int = 16):
        self.oracle = Oracle(ROOT / "oracle_tmp")
        self.cache_path = SCORED / "oracle_cache.jsonl"
        self.cache = {r["key"]: r for r in read_jsonl(self.cache_path)}
        self.n_threads = n_threads

    def score_records(self, recs: list[dict]) -> list[dict]:
        cls_list = [classify_text(r["text"]) for r in recs]
        todo = {}
        for r, c in zip(recs, cls_list):
            if c.get("code") is not None and c["label"] != "syntax_error":
                key = r["task"] + ":" + hashlib.sha1(c["code"].encode()).hexdigest()
                if key not in self.cache:
                    todo[key] = (r["task"], c["code"])
        if todo:
            args = [(str(self.oracle.workdir), str(self.oracle.harness), str(self.oracle.inst_paths[t]), t,
                     TASKS[t]["func"], code, k) for k, (t, code) in todo.items()]
            with ThreadPoolExecutor(self.n_threads) as ex:
                outs = list(ex.map(run_one, args))
            new = []
            for o in outs:
                task = o["uid"].split(":")[0]
                res = self.oracle.check(task, o["recs"])
                rec = {"key": o["uid"], "status": o["status"], **res}
                self.cache[o["uid"]] = rec
                new.append(rec)
            append_jsonl(self.cache_path, new)
        out = []
        for r, c in zip(recs, cls_list):
            res = {"pass": False, "frac_correct": 0.0, "frac_shortest": 0.0, "status": "no_code"}
            code_hash = None
            if c.get("code") is not None and c["label"] != "syntax_error":
                code_hash = hashlib.sha1(c["code"].encode()).hexdigest()
                res = self.cache[r["task"] + ":" + code_hash]
            deg = degeneration_flags(r["text"], r["ntoks"], r["hit_max"], c, TASKS[r["task"]]["func"])
            out.append({"setting": r["setting"], "task": r["task"], "idx": r["idx"], "label": c["label"],
                        "pass": bool(res["pass"]), "frac_correct": res["frac_correct"],
                        "frac_shortest": res["frac_shortest"], "oracle_status": res.get("status"),
                        "code_hash": code_hash, "stripped": c.get("stripped", "")[:6000], "extract": c.get("extract"),
                        "ntoks": r["ntoks"], **{f"deg_{k}": v for k, v in deg.items()}})
        return out


def entropy_bits(counts: dict) -> float:
    n = sum(counts.values())
    if n == 0:
        return 0.0
    return -sum((c / n) * math.log2(c / n) for c in counts.values() if c > 0)
