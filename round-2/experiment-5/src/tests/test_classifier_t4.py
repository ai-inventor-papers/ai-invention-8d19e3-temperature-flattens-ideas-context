"""Fixtures for classifier v1+T4 (>=2 per class, incl. tricky ones) + T4 oracle tests. Must pass 100%."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from classify_t4 import classify_t4  # noqa: E402
from oracle_t4 import run_many  # noqa: E402


def fence(code: str) -> str:
    return "Here is an implementation:\n\n```python\n" + code.strip() + "\n```\n\nThis works in O(n)."


FIX: list[tuple[str, str, str]] = [
    ("quickselect_lists", "Quickselect", '''
import random
def kth_smallest(arr, k):
    """Quickselect: sorted() is NOT used here."""
    if k < 1 or k > len(arr):
        raise ValueError("k out of range")
    pivot = random.choice(arr)
    lows = [x for x in arr if x < pivot]
    highs = [x for x in arr if x > pivot]
    pivots = [x for x in arr if x == pivot]
    if k <= len(lows):
        return kth_smallest(lows, k)
    elif k <= len(lows) + len(pivots):
        return pivots[0]
    return kth_smallest(highs, k - len(lows) - len(pivots))
'''),
    ("quickselect_lomuto", "Quickselect", '''
def partition(arr, low, high):
    pivot = arr[high]
    i = low - 1
    for j in range(low, high):
        if arr[j] <= pivot:
            i += 1
            arr[i], arr[j] = arr[j], arr[i]
    arr[i + 1], arr[high] = arr[high], arr[i + 1]
    return i + 1

def quickselect(arr, low, high, k):
    if low == high:
        return arr[low]
    p = partition(arr, low, high)
    if p == k:
        return arr[p]
    elif k < p:
        return quickselect(arr, low, p - 1, k)
    return quickselect(arr, p + 1, high, k)

def find_kth_smallest(arr, k):
    return quickselect(arr, 0, len(arr) - 1, k - 1)
'''),
    ("quickselect_hoare_random", "Quickselect", '''
import random
def kth_smallest(nums, k):
    target = k - 1
    lo, hi = 0, len(nums) - 1
    while True:
        r = random.randint(lo, hi)
        nums[r], nums[hi] = nums[hi], nums[r]
        pivot = nums[hi]
        store = lo
        for i in range(lo, hi):
            if nums[i] < pivot:
                nums[store], nums[i] = nums[i], nums[store]
                store += 1
        nums[store], nums[hi] = nums[hi], nums[store]
        if store == target:
            return nums[store]
        elif store < target:
            lo = store + 1
        else:
            hi = store - 1
'''),
    ("heap_nsmallest_tricky", "Heap_select", '''
import heapq
def kth_smallest(a, k):
    return heapq.nsmallest(k, a)[-1]
'''),
    ("heap_heapify_pop", "Heap_select", '''
import heapq
def kth_smallest(arr, k):
    h = list(arr)
    heapq.heapify(h)
    for _ in range(k - 1):
        heapq.heappop(h)
    return h[0]
'''),
    ("heap_maxheap_k", "Heap_select", '''
import heapq
def find_kth_smallest(nums, k):
    heap = []
    for x in nums:
        heapq.heappush(heap, -x)
        if len(heap) > k:
            heapq.heappop(heap)
    return -heap[0]
'''),
    ("sort_index_sorted", "Sort_index", '''
def kth_smallest(arr, k):
    if k <= 0 or k > len(arr):
        return None
    return sorted(arr)[k - 1]
'''),
    ("sort_index_set_tricky", "Sort_index", '''
def kth_smallest(arr, k):
    return sorted(set(arr))[k - 1]
'''),
    ("sort_index_quicksort_impl", "Sort_index", '''
def quicksort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left) + middle + quicksort(right)

def kth_smallest(arr, k):
    if k < 1 or k > len(arr):
        raise IndexError("k is out of bounds")
    return quicksort(arr)[k - 1]
'''),
    ("sort_index_bubble_impl", "Sort_index", '''
def kth_smallest(arr, k):
    n = len(arr)
    for i in range(n):
        for j in range(0, n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr[k - 1]
'''),
    ("mom_classic", "Median_of_medians", '''
def select(arr, k):
    if len(arr) <= 5:
        return sorted(arr)[k]
    chunks = [arr[i:i + 5] for i in range(0, len(arr), 5)]
    medians = [sorted(c)[len(c) // 2] for c in chunks]
    pivot = select(medians, len(medians) // 2)
    lows = [x for x in arr if x < pivot]
    highs = [x for x in arr if x > pivot]
    pivots = [x for x in arr if x == pivot]
    if k < len(lows):
        return select(lows, k)
    elif k < len(lows) + len(pivots):
        return pivot
    return select(highs, k - len(lows) - len(pivots))

def kth_smallest(arr, k):
    return select(arr, k - 1)
'''),
    ("mom_named", "Median_of_medians", '''
def median_of_medians(arr, k):
    groups = [arr[i:i + 5] for i in range(0, len(arr), 5)]
    meds = [sorted(g)[len(g) // 2] for g in groups]
    if len(meds) <= 5:
        pivot = sorted(meds)[len(meds) // 2]
    else:
        pivot = median_of_medians(meds, len(meds) // 2 + 1)
    low = [x for x in arr if x < pivot]
    high = [x for x in arr if x > pivot]
    eq = len(arr) - len(low) - len(high)
    if k <= len(low):
        return median_of_medians(low, k)
    if k <= len(low) + eq:
        return pivot
    return median_of_medians(high, k - len(low) - eq)
'''),
    ("partial_min_remove", "Partial_selection", '''
def kth_smallest(arr, k):
    a = list(arr)
    for _ in range(k - 1):
        a.remove(min(a))
    return min(a)
'''),
    ("partial_selection_sort_k", "Partial_selection", '''
def kth_smallest(arr, k):
    for i in range(k):
        min_idx = i
        for j in range(i + 1, len(arr)):
            if arr[j] < arr[min_idx]:
                min_idx = j
        arr[i], arr[min_idx] = arr[min_idx], arr[i]
    return arr[k - 1]
'''),
    ("counting_array", "Counting_bucket", '''
def kth_smallest(arr, k):
    lo, hi = min(arr), max(arr)
    count = [0] * (hi - lo + 1)
    for x in arr:
        count[x - lo] += 1
    total = 0
    for i, c in enumerate(count):
        total += c
        if total >= k:
            return i + lo
'''),
    ("counting_counter", "Counting_bucket", '''
from collections import Counter
def kth_smallest(arr, k):
    cnt = Counter(arr)
    running = 0
    for v in sorted(cnt):
        running += cnt[v]
        if running >= k:
            return v
'''),
    ("bsv_classic", "Binary_search_value", '''
def kth_smallest(arr, k):
    lo, hi = min(arr), max(arr)
    while lo < hi:
        mid = (lo + hi) // 2
        cnt = sum(1 for x in arr if x <= mid)
        if cnt < k:
            lo = mid + 1
        else:
            hi = mid
    return lo
'''),
    ("bsv_count_fn", "Binary_search_value", '''
def count_le(arr, value):
    return len([x for x in arr if x <= value])

def find_kth_smallest(arr, k):
    left, right = min(arr), max(arr)
    while left <= right:
        mid = left + (right - left) // 2
        if count_le(arr, mid) >= k:
            right = mid - 1
        else:
            left = mid + 1
    return left
'''),
    ("builtin_numpy", "Builtin", '''
import numpy as np
def kth_smallest(arr, k):
    return np.partition(np.array(arr), k - 1)[k - 1]
'''),
    ("builtin_pandas", "Builtin", '''
import pandas as pd
def kth_smallest(arr, k):
    return pd.Series(arr).nsmallest(k).iloc[-1]
'''),
    ("other_brute", "Other", '''
def kth_smallest(arr, k):
    for x in arr:
        smaller = 0
        equal = 0
        for y in arr:
            if y < x:
                smaller += 1
            elif y == x:
                equal += 1
        if smaller < k <= smaller + equal:
            return x
'''),
    ("unparseable_prose", "Unparseable", None),
]


def test_fixtures() -> None:
    bad = []
    for name, want, code in FIX:
        text = "I cannot write code for that, but quickselect is a good idea." if code is None else fence(code)
        got = classify_t4(text)["label"]
        if got != want:
            bad.append((name, want, got))
    assert not bad, bad


ORACLE_PROGS = {
    "correct_quickselect": (FIX[0][2], "pass"),
    "correct_heap": (FIX[4][2], "pass"),
    "zero_indexed": ("def kth_smallest(arr, k):\n    return sorted(arr)[k] if k < len(arr) else None\n", "fail0"),
    "off_by_one": ("def kth_smallest(arr, k):\n    return sorted(arr)[max(k - 2, 0)]\n", "fail"),
    "infinite_loop": ("def kth_smallest(arr, k):\n    while True:\n        pass\n", "timeout"),
    "no_function": ("x = [3, 1, 2]\nprint(sorted(x)[1])\n", "not_callable"),
}


def test_oracle() -> None:
    names = list(ORACLE_PROGS)
    res = run_many([ORACLE_PROGS[n][0] for n in names], workers=6)
    bad = []
    for n, r in zip(names, res):
        want = ORACLE_PROGS[n][1]
        ok = {"pass": r["passed"], "fail0": (not r["passed"]) and r["pass_0idx"],
              "fail": (not r["passed"]) and not r["pass_0idx"] and r["status"] == "fail",
              "timeout": r["status"] == "timeout", "not_callable": r["status"] == "not_callable"}[want]
        if not ok:
            bad.append((n, want, r))
    assert not bad, bad


if __name__ == "__main__":
    test_fixtures()
    print(f"T4 classifier fixtures: {len(FIX)}/{len(FIX)} pass")
    test_oracle()
    print(f"T4 oracle tests: {len(ORACLE_PROGS)}/{len(ORACLE_PROGS)} pass")
