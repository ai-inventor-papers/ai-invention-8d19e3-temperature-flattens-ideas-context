"""Extended condition builder: T1-T4, new condition types (alt placebo, mention, cross-domain) on the SAME
chat template. For every condition that exists in protocol.py the string is produced by protocol.user_message
(byte-identical to the screen)."""
from __future__ import annotations

import protocol as P
from protocol_t4 import BANNABLE_T4, DISPLAY_T4, PLACEBO_T4, TASK_T4, TAXONOMY_SELECT

TASKS_ALL = dict(P.TASKS, T4=TASK_T4)
KIND_ALL = dict(P.TASK_KIND, T4="select")
DISPLAY_ALL = dict(P.DISPLAY, **DISPLAY_T4)
ALT_PLACEBO = "Do not use the Huffman coding algorithm."
CROSS = {"T1": "Do not use quicksort.", "T2": "Do not use Dijkstra's algorithm."}


def taxonomy(task: str) -> list[str]:
    return TAXONOMY_SELECT if task == "T4" else P.taxonomy(task)


def bannable(task: str) -> list[str]:
    return list(BANNABLE_T4) if task == "T4" else P.bannable(task)


def ban_sentence(task: str, classes: list[str]) -> str:
    order = taxonomy(task)
    cl = sorted(classes, key=order.index)
    return f"Do not use {P.join_names([DISPLAY_ALL[c] for c in cl])}."


def user_message(task: str, condition: str, banned: list[str] | None = None) -> str:
    """condition: baseline | placebo | alt_placebo | mention_<C> | cross | forced_<C> | comention | ban_* | pair_*."""
    if condition.startswith("placebo_b"):  # confirmation placebo blocks: same text, different seed blocks
        condition = "placebo"
    if task != "T4" and condition in ("baseline", "placebo", "comention", "para1_r1", "para2_r1") \
            or (task != "T4" and condition.startswith("forced_")):
        return P.user_message(task, condition, banned)
    base = TASKS_ALL[task]
    if condition == "baseline":
        return base
    if condition == "placebo":
        return base + " " + PLACEBO_T4
    if condition == "alt_placebo":
        return base + " " + ALT_PLACEBO
    if condition == "cross":
        return base + " " + CROSS[task]
    if condition.startswith("mention_"):
        return base + " " + f"You may use {DISPLAY_ALL[condition[len('mention_'):]]}."
    if condition.startswith("forced_"):
        return base + " using " + DISPLAY_ALL[condition[len("forced_"):]] + "."
    if condition == "comention":
        return ("List 10 algorithms that could solve this task: " + base
                + ". Reply with only a numbered list of algorithm names.")
    assert banned, condition
    if condition in ("ban_top3", "ban_top5") or len(banned) == 1:  # rank order, as in the screen
        return base + " " + f"Do not use {P.join_names([DISPLAY_ALL[c] for c in banned])}."
    return base + " " + ban_sentence(task, banned)  # pairs: taxonomy order
