"""Reserved task T4 (k-th smallest element) + its 'select' taxonomy. protocol.py stays byte-identical."""
from __future__ import annotations

TASK_T4 = "Implement a function that finds the k-th smallest element in a list"
TAXONOMY_SELECT = ["Quickselect", "Heap_select", "Sort_index", "Median_of_medians", "Partial_selection",
                   "Counting_bucket", "Binary_search_value", "Builtin", "Other"]
DISPLAY_T4 = {
    "Quickselect": "quickselect", "Heap_select": "a heap", "Sort_index": "sorting",
    "Median_of_medians": "the median-of-medians algorithm", "Partial_selection": "repeated minimum selection",
    "Counting_bucket": "counting or bucketing", "Binary_search_value": "binary search on the value range",
}
PLACEBO_T4 = "Do not use the Rabin-Karp algorithm."
BANNABLE_T4 = [c for c in TAXONOMY_SELECT if c not in ("Builtin", "Other")]
