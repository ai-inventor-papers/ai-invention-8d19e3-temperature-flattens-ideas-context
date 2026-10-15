"""Unit tests: classifier on reference implementations, oracle on correct/wrong/hostile programs."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from protocol.classifier import classify_program, classify_text
from protocol.oracle import Oracle, run_one

def main():
    refs = sorted((ROOT / "tests/refs").glob("*.py"))
    bad = 0
    for p in refs:
        name = p.stem.rsplit("_", 1)[0]
        lab = classify_program(p.read_text())["label"]
        if name in ("wrong_skip", "infinite", "input"):
            continue
        ok = lab == name
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} {p.name:28s} -> {lab}")
    txt = "Here is code:\n```python\n" + (ROOT / "tests/refs/bfs_1.py").read_text() + "```\nDone."
    assert classify_text(txt)["label"] == "bfs"
    ora = Oracle(ROOT / "tests/_oracle_tmp")
    expect = {"bfs_1": True, "bfs_2": True, "dfs_1": True, "dfs_2": True, "iddfs_1": False, "bidirectional_1": True,
              "greedy_best_first_1": True, "wrong_skip_edge": False, "infinite_loop": False, "input_exit": False,
              "dijkstra_1": True, "dijkstra_2": True, "bellman_ford_1": True, "spfa_1": True, "floyd_warshall_1": True, "astar_1": True}
    for p in refs:
        task = "T3" if "shortest_path" in p.read_text() else "T1"
        func = "shortest_path" if task == "T3" else "find_path"
        r = run_one((str(ora.workdir), str(ora.harness), str(ora.inst_paths[task]), task, func, p.read_text(), p.stem))
        res = ora.check(task, r["recs"])
        ok = res["pass"] == expect[p.stem]
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} oracle {p.stem:22s} {task} {res} {r['status']}")
    print("FAILURES:", bad)
    return bad

if __name__ == "__main__":
    sys.exit(1 if main() else 0)
