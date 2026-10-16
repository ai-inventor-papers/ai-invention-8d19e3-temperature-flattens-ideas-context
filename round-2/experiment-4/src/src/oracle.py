"""Execution oracle driver: runs each program in an isolated subprocess (python -I, RLIMIT_AS 1GB, RLIMIT_CPU 10s).

The oracle validates correctness for pass-rate and outside-menu analyses; it NEVER relabels ideas.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HARNESS = Path(__file__).resolve().parent / "oracle_harness.py"
FAIL = dict(callable=False, convention=None, n_tests=0, n_pass=0, pass_frac=0.0, shortest_rate=None, passed=False)


def run_one(code: str, task: str, tmpdir: str, wall: float = 30.0) -> dict:
    if not code or not code.strip():
        return dict(FAIL, error="no_code")
    fd, cf = tempfile.mkstemp(suffix=".py", dir=tmpdir)
    os.close(fd)
    rf = cf + ".json"
    Path(cf).write_text(code)
    try:
        subprocess.run([sys.executable, "-I", str(HARNESS), cf, task, rf], cwd=tmpdir, timeout=wall,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        if Path(rf).exists():
            res = json.loads(Path(rf).read_text())
        else:
            res = dict(FAIL, error="no_result (crash/rlimit)")
    except subprocess.TimeoutExpired:
        res = dict(FAIL, error="wall_timeout")
    except (OSError, json.JSONDecodeError) as e:
        res = dict(FAIL, error=repr(e)[:200])
    finally:
        for p in (cf, rf):
            try:
                os.remove(p)
            except OSError:
                pass
    return res


def run_many(items: list[tuple[str, str]], workers: int = 8) -> list[dict]:
    """items: list of (code, task). Returns results in order."""
    root = Path(__file__).resolve().parent.parent / "data" / "oracle_tmp"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as td:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(lambda it: run_one(it[0], it[1], td), items))
