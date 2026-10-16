"""Execution oracle for T4 (k-th smallest). Each program runs in an isolated subprocess (python -I,
RLIMIT_AS 1 GB, RLIMIT_CPU 10 s, 1 s alarm per call). 50 instances from seed 12345: lists of length 1..60,
values in [-50, 50] (heavy duplicates), 5 all-equal lists, k in {1, len, random}. pass = f(copy(a), k) ==
sorted(a)[k-1] on all 50; pass_0idx = f(copy(a), k) == sorted(a)[k] on every instance with k < len (secondary).
Status in {pass, fail, not_callable, timeout, error}. The oracle validates correctness only; it never relabels.

Usage as harness: python -I oracle_t4.py <code_file> <result_json>
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def instances() -> list[tuple[list[int], int]]:
    import random
    rng = random.Random(12345)
    out = []
    for i in range(45):
        n = rng.randint(1, 60)
        a = [rng.randint(-50, 50) for _ in range(n)]
        k = [1, n, rng.randint(1, n)][i % 3]
        out.append((a, k))
    for i in range(5):
        n = rng.randint(1, 30)
        v = rng.randint(-50, 50)
        out.append(([v] * n, [1, n, rng.randint(1, n), 1, n][i]))
    return out


# ------------------------------------------------------------------------------------------- harness side
def _harness(code_file: str, res_file: str) -> None:
    import builtins
    import inspect
    import re
    import resource
    import signal

    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    res = dict(status="error", callable=None, n_pass=0, n_tests=0, passed=False, pass_0idx=False, error=None)

    def write():
        Path(res_file).write_text(json.dumps(res))

    class TO(Exception):
        pass

    def alarm(*_):
        raise TO()

    signal.signal(signal.SIGALRM, alarm)
    builtins.input = lambda *a, **k: (_ for _ in ()).throw(EOFError())
    sys.stdin = open(os.devnull)
    devnull = open(os.devnull, "w")
    code = Path(code_file).read_text()
    g = {"__name__": "__oracle__"}
    try:
        signal.setitimer(signal.ITIMER_REAL, 3.0)
        old = sys.stdout
        sys.stdout = devnull
        try:
            exec(compile(code, "prog", "exec"), g)
        finally:
            sys.stdout = old
            signal.setitimer(signal.ITIMER_REAL, 0)
    except TO:
        res.update(status="timeout", error="module_timeout")
        write()
        return
    except BaseException as e:  # noqa: BLE001 - arbitrary model code
        res.update(status="error", error=f"exec: {type(e).__name__}: {str(e)[:120]}")
        write()
        return

    cands = []
    for name, obj in list(g.items()):
        if name.startswith("_") or not inspect.isfunction(obj):
            continue
        if getattr(obj, "__code__", None) is None or obj.__code__.co_filename != "prog":
            continue
        try:
            ps = [p for p in inspect.signature(obj).parameters.values()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        except (TypeError, ValueError):
            continue
        req = [p for p in ps if p.default is p.empty]
        if len(ps) >= 2 and len(req) <= 2:
            pref = 0 if re.search(r"kth|k_th|smallest|select", name, re.I) else 1
            cands.append((pref, obj.__code__.co_firstlineno, name, obj, len(req)))
    if not cands:
        res.update(status="not_callable")
        write()
        return
    cands.sort(key=lambda c: (c[0], -c[1]))  # preferred names first, then the LAST defined (usually the entry)
    insts = instances()

    def call(fn, a, k, order):
        signal.setitimer(signal.ITIMER_REAL, 1.0)
        old = sys.stdout
        sys.stdout = devnull
        try:
            return fn(list(a), k) if order == 0 else fn(k, list(a))
        finally:
            sys.stdout = old
            signal.setitimer(signal.ITIMER_REAL, 0)

    best = None
    for pref, _, name, fn, nreq in cands[:4]:
        for order in (0, 1):
            npass = n0 = n0t = 0
            status = "fail"
            err = None
            for a, k in insts:
                try:
                    r = call(fn, a, k, order)
                except TO:
                    status, err = "timeout", "call_timeout"
                    break
                except RecursionError:
                    err = "recursion"
                    continue
                except BaseException as e:  # noqa: BLE001
                    err = f"{type(e).__name__}: {str(e)[:80]}"
                    continue
                s = sorted(a)
                try:
                    if r == s[k - 1]:
                        npass += 1
                    if k < len(a):
                        n0t += 1
                        if r == s[k]:
                            n0 += 1
                except BaseException:  # noqa: BLE001 - weird return types
                    pass
            cand = dict(callable=name, order=order, n_pass=npass, n_tests=len(insts), status=status, error=err,
                        passed=npass == len(insts), pass_0idx=(n0t > 0 and n0 == n0t))
            if best is None or (cand["n_pass"], cand["pass_0idx"]) > (best["n_pass"], best["pass_0idx"]):
                best = cand
            if cand["passed"]:
                break
        if best and best["passed"]:
            break
    if best["passed"]:
        best["status"] = "pass"
    elif best["status"] != "timeout":
        best["status"] = "fail" if best["n_pass"] > 0 or best["pass_0idx"] or best["error"] is None else "error"
    res.update(best)
    write()


# ------------------------------------------------------------------------------------------- driver side
FAIL = dict(status="not_callable", callable=None, n_pass=0, n_tests=50, passed=False, pass_0idx=False)


def run_one(code: str, tmpdir: str, wall: float = 60.0) -> dict:
    if not code or not code.strip():
        return dict(FAIL, error="no_code")
    fd, cf = tempfile.mkstemp(suffix=".py", dir=tmpdir)
    os.close(fd)
    rf = cf + ".json"
    Path(cf).write_text(code)
    try:
        subprocess.run([sys.executable, "-I", str(Path(__file__).resolve()), cf, rf], cwd=tmpdir, timeout=wall,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        res = json.loads(Path(rf).read_text()) if Path(rf).exists() else dict(FAIL, status="error",
                                                                              error="no_result (crash/rlimit)")
    except subprocess.TimeoutExpired:
        res = dict(FAIL, status="timeout", error="wall_timeout")
    except (OSError, json.JSONDecodeError) as e:
        res = dict(FAIL, status="error", error=repr(e)[:200])
    finally:
        for p in (cf, rf):
            try:
                os.remove(p)
            except OSError:
                pass
    return res


def run_many(codes: list[str], workers: int = 8) -> list[dict]:
    root = Path(__file__).resolve().parent.parent / "data" / "oracle_tmp"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as td:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(lambda c: run_one(c, td), codes))


if __name__ == "__main__":
    _harness(sys.argv[1], sys.argv[2])
