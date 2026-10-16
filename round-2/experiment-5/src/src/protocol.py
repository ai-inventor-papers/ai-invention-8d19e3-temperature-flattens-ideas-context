"""SHARED PROTOCOL CONSTANTS (frozen before any run). Do not edit after generation starts."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
GEN = DATA / "gen"
ACTS = DATA / "acts"
RESULTS = ROOT / "results"
FIGS = ROOT / "figures"
LOGS = ROOT / "logs"

MODEL = "Qwen/Qwen2.5-3B-Instruct"  # 36 layers, d=2048, tied embeddings, vocab 151936

TASKS: dict[str, str] = {
    "T1": "Implement a path search algorithm in Python",
    "T2": "Implement a sorting algorithm",
    "T3": "Implement a function that finds a shortest path in a weighted graph",
}
TASK_KIND = {"T1": "graph", "T2": "sort", "T3": "graph"}

TEMPERATURE = 0.7
TOP_P = 1.0
TOP_K = -1
MAX_TOKENS = 768

TAXONOMY_GRAPH = ["BFS", "DFS", "IDDFS", "Dijkstra", "A_star", "Greedy_best_first", "Bidirectional",
                  "Bellman_Ford", "SPFA", "Floyd_Warshall", "Other"]
TAXONOMY_SORT = ["Quick", "Merge", "Heap", "Insertion", "Selection", "Bubble", "Shell", "Counting",
                 "Radix", "Bucket", "Tim_hybrid", "Builtin", "Other"]

DISPLAY: dict[str, str] = {
    "BFS": "breadth-first search (BFS)", "DFS": "depth-first search (DFS)", "IDDFS": "iterative deepening DFS",
    "Dijkstra": "Dijkstra's algorithm", "A_star": "A* search", "Greedy_best_first": "greedy best-first search",
    "Bidirectional": "bidirectional search", "Bellman_Ford": "the Bellman-Ford algorithm", "SPFA": "SPFA",
    "Floyd_Warshall": "the Floyd-Warshall algorithm",
    "Quick": "quicksort", "Merge": "merge sort", "Heap": "heap sort", "Insertion": "insertion sort",
    "Selection": "selection sort", "Bubble": "bubble sort", "Shell": "shell sort", "Counting": "counting sort",
    "Radix": "radix sort", "Bucket": "bucket sort", "Tim_hybrid": "Timsort",
}

NON_IDEA = ["Unparseable"]
PLACEBO = {"T1": "Do not use the Rabin-Karp algorithm.", "T2": "Do not use Kruskal's algorithm.",
           "T3": "Do not use the Rabin-Karp algorithm."}

N_BASELINE = 300
N_BAN = 100
N_COMENTION = 50
N_FORCED = 10  # cut from 20 (fallback order) after vLLM toolchain failure cost ~1h
LAYERS = [4, 8, 12, 16, 20, 24, 28, 32, 36]

BAN_CONDITIONS = ["ban_r1", "ban_r2", "ban_r3", "ban_r4", "ban_top3", "ban_top5", "ban_rare", "placebo",
                  "para1_r1", "para2_r1"]
FIT_CONDITIONS = ["ban_r1", "ban_r2", "ban_r3", "ban_r4", "ban_top3", "ban_top5", "ban_rare"]


def taxonomy(task: str) -> list[str]:
    return TAXONOMY_GRAPH if TASK_KIND[task] == "graph" else TAXONOMY_SORT


def bannable(task: str) -> list[str]:
    return [c for c in taxonomy(task) if c not in ("Other", "Builtin")]


def join_names(names: list[str]) -> str:
    """'A' | 'A or B' | 'A, B or C' (no Oxford comma)."""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " or " + names[-1]


def ban_sentence(classes: list[str]) -> str:
    return f"Do not use {join_names([DISPLAY[c] for c in classes])}."


def user_message(task: str, condition: str, banned: list[str] | None = None) -> str:
    base = TASKS[task]
    if condition == "baseline":
        return base
    if condition == "placebo":
        return base + " " + PLACEBO[task]
    if condition == "para1_r1":
        return base + " " + f"Avoid using {DISPLAY[banned[0]]}."
    if condition == "para2_r1":
        return base + " " + f"Your solution must not use {DISPLAY[banned[0]]} or close variants of it."
    if condition.startswith("forced_"):
        return base + " using " + DISPLAY[condition[len("forced_"):]] + "."
    if condition == "comention":
        return ("List 10 algorithms that could solve this task: " + base
                + ". Reply with only a numbered list of algorithm names.")
    assert banned, condition
    return base + " " + ban_sentence(banned)
