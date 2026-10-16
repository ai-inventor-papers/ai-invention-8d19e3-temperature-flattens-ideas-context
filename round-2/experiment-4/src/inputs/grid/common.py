"""Shared constants, paths, logging and IO helpers for all stages."""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
LOGS = ROOT / "logs"
FIG = ROOT / "figures"
RESULTS = ROOT / "results"
ACTS = ROOT / "activations"
PROBES = ROOT / "probes"
for _d in (CONFIG, DATA, LOGS, FIG, RESULTS, ACTS, PROBES):
    _d.mkdir(parents=True, exist_ok=True)

MODEL = "Qwen/Qwen2.5-3B-Instruct"
PROMPTS = {
    "T1": "Implement a path search algorithm in Python.",
    "T2": "Implement a sorting algorithm in Python.",
    "T3": "Implement a function in Python that finds the shortest path in a weighted graph with non-negative edge weights.",
}
TASKS = ["T1", "T2", "T3"]
TEMPS = [0.3, 0.5, 0.7, 1.0, 1.3, 1.6]
TOPKS = [10, -1]
N_PER_CELL = 100
N_EXT = 300
MAX_TOKENS = 768
FORK_POSITIONS = 48
FORK_ROLLOUTS = 8
FORK_PER_TASK = 30
FORK_ROLLOUT_TOKENS = 320
FORK_T = 0.7


def setup_logging(name: str) -> None:
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
    logger.add(LOGS / f"{name}.log", rotation="30 MB", level="DEBUG")


def cgroup_cpus() -> int:
    try:
        parts = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if parts[0] != "max":
            return math.ceil(int(parts[0]) / int(parts[1]))
    except (FileNotFoundError, ValueError):
        pass
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def set_ram_limit(gb: float) -> None:
    import resource
    b = int(gb * 1024 ** 3)
    resource.setrlimit(resource.RLIMIT_AS, (b, b))


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def write_jsonl(p: Path, rows: list[dict]) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    tmp.replace(p)


def load_json(p: Path):
    return json.loads(p.read_text())


def save_json(p: Path, obj) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=_json_default))
    tmp.replace(p)


def _json_default(o):
    import numpy as np
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        f = float(o)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, tuple)):
        return list(o)
    raise TypeError(f"not serializable: {type(o)}")


def path_labels(task: str) -> list[str]:
    from ideaclf.classify import PATH_LABELS, SORT_LABELS
    return SORT_LABELS if task == "T2" else PATH_LABELS
