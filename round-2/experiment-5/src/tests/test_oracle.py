"""Oracle tests: reference implementations pass; deliberately buggy ones fail."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from oracle import run_many  # noqa: E402
from test_classifier import GRAPH, SORT  # noqa: E402

BUGGY_DIJKSTRA = '''import heapq
def dijkstra(graph, start, goal):
    dist = {start: 0}; prev = {}
    pq = [(0, start)]; visited = set()
    while pq:
        d, u = heapq.heappop(pq)
        visited.add(u)
        for v, w in graph[u].items():
            if v not in dist:          # bug: never relaxes, first-found distance kept
                dist[v] = d + w; prev[v] = u
                heapq.heappush(pq, (d + w, v))
    if goal not in dist: return None
    path = [goal]
    while path[-1] != start: path.append(prev[path[-1]])
    return dist[goal], path[::-1]'''
BUGGY_BUBBLE = '''def bubble_sort(arr):
    n = len(arr)
    for i in range(n - 1):
        for j in range(0, n - i - 2):   # off-by-one
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr'''

def main():
    items, names = [], []
    # IDDFS with path-sets is exponential: may time out on 1-2 dense graphs (pass_frac >= 0.9 accepted)
    for c in ["BFS", "DFS", "A_star", "Bidirectional"]:
        items.append((GRAPH[c][0], "T1")); names.append(("T1", c, True))
    for c in ["Dijkstra", "SPFA", "Bellman_Ford"]:
        items.append((GRAPH[c][0], "T3")); names.append(("T3", c, True))
    items.append((GRAPH["Dijkstra"][0], "T1")); names.append(("T1", "Dijkstra", True))
    for c in ["Quick", "Merge", "Heap", "Insertion", "Bubble", "Shell", "Counting", "Bucket", "Tim_hybrid", "Builtin", "Selection"]:
        items.append((SORT[c][0], "T2")); names.append(("T2", c, True))
    # reference radix sort handles non-negative ints only -> must FAIL on lists with negatives
    items.append((SORT["Radix"][0], "T2")); names.append(("T2", "Radix(nonneg-only)", False))
    items.append((BUGGY_DIJKSTRA, "T3")); names.append(("T3", "BUGGY_DIJKSTRA", False))
    items.append((BUGGY_BUBBLE, "T2")); names.append(("T2", "BUGGY_BUBBLE", False))
    res = run_many(items)
    bad = 0
    for (t, c, exp), r in zip(names, res):
        flag = "OK " if r["passed"] == exp else "BAD"
        bad += r["passed"] != exp
        print(flag, t, c, r.get("convention"), r.get("pass_frac"), r.get("error", ""), r.get("load_error"))
    print("failures:", bad)
    return bad

if __name__ == "__main__":
    sys.exit(main())
