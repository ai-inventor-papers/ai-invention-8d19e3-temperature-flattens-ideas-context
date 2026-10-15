"""Shared protocol: task prompts, output contracts, condition texts, idea taxonomy.

Every condition appends ONLY its condition text between TASK and CONTRACT, so the
engine, chat template, contract and token budget are held constant.
"""

from __future__ import annotations

import json
from pathlib import Path

MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"
MAX_NEW_TOKENS = 768

TASKS: dict[str, dict[str, str]] = {
    "T1": {
        "task": "Implement a path search algorithm in Python.",
        "contract": (
            "Write a function find_path(graph, start, goal) where graph is a dict mapping each node to a "
            "list of neighbouring nodes (directed edges). Return a list of nodes from start to goal "
            "(inclusive) that follows existing edges, or None if goal is unreachable. Put the complete "
            "code in a single ```python code block."
        ),
        "func": "find_path",
    },
    "T3": {
        "task": "Implement a function that finds a shortest path in a weighted graph.",
        "contract": (
            "Write a function shortest_path(graph, source, target) in Python where graph is a dict mapping "
            "each node to a list of (neighbour, weight) pairs with non-negative weights. Return a tuple "
            "(distance, path) with path a list of nodes from source to target, or (float(\"inf\"), None) if "
            "unreachable. Put the complete code in a single ```python code block."
        ),
        "func": "shortest_path",
    },
}

# Used only for A4 direction extraction (never generated from, never a path task).
T2_TASK = "Implement a sorting algorithm in Python."

COND_TEXT: dict[str, str] = {
    "plain": "",
    "new": "Make a new algorithm.",
    "novel2000": (
        "Make a fully novel algorithm never seen before. Explain the idea in detail (about 2000 words) "
        "and implement it."
    ),
    # ban3 is filled with the top-3 classes of THIS arm's T=0.7 baseline after step 1.
    "ban3": "Do not use any of the following algorithms: {A}, {B}, {C}.",
}

GTS_STAGE1_SUFFIX = (
    " List 10 distinct approaches you could use, one per line, numbered 1-10, each a name plus one "
    "sentence. Do not write code."
)
GTS_STAGE2_TEMPLATE = "{task} Use this approach: {item}\n\n{contract}"

# Idea taxonomy (ordered = classifier rule order; first match wins).
TAXONOMY: list[str] = [
    "floyd_warshall", "bellman_ford", "spfa", "bidirectional", "astar", "greedy_best_first",
    "dijkstra", "dial_bucket", "iddfs", "bfs", "dfs", "random_walk", "other",
]
DISPLAY_NAME: dict[str, str] = {
    "floyd_warshall": "Floyd-Warshall", "bellman_ford": "Bellman-Ford",
    "spfa": "SPFA (queue-based Bellman-Ford)", "bidirectional": "bidirectional search",
    "astar": "A* search", "greedy_best_first": "greedy best-first search", "dijkstra": "Dijkstra's algorithm",
    "dial_bucket": "Dial's bucket algorithm", "iddfs": "iterative deepening DFS",
    "bfs": "breadth-first search (BFS)", "dfs": "depth-first search (DFS)", "random_walk": "random walk search",
    "other": "other",
}

NOVEL_HINT_A4 = "Make a fully novel algorithm never seen before."


def build_user_prompt(task_key: str, cond: str = "plain", cond_text: str | None = None) -> str:
    """TASK + (' ' + COND_TEXT if any) + '\\n\\n' + CONTRACT."""
    t = TASKS[task_key]
    text = COND_TEXT[cond] if cond_text is None else cond_text
    mid = (" " + text) if text else ""
    return t["task"] + mid + "\n\n" + t["contract"]


def gts_stage1_prompt(task_key: str) -> str:
    return TASKS[task_key]["task"] + GTS_STAGE1_SUFFIX


def gts_stage2_prompt(task_key: str, item: str) -> str:
    t = TASKS[task_key]
    return GTS_STAGE2_TEMPLATE.format(task=t["task"], item=item.strip(), contract=t["contract"])


def write_protocol_json(path: Path, extra: dict | None = None) -> None:
    d = {
        "model": MODEL_ID, "max_new_tokens": MAX_NEW_TOKENS, "tasks": TASKS, "T2_TASK": T2_TASK,
        "cond_text": COND_TEXT, "gts_stage1_suffix": GTS_STAGE1_SUFFIX, "gts_stage2_template": GTS_STAGE2_TEMPLATE,
        "taxonomy": TAXONOMY, "display_name": DISPLAY_NAME, "novel_hint_a4": NOVEL_HINT_A4,
        "prompt_rule": "TASK + (' ' + COND_TEXT if any) + '\\n\\n' + CONTRACT; chat template with default system prompt",
    }
    if extra:
        d.update(extra)
    path.write_text(json.dumps(d, indent=2))
