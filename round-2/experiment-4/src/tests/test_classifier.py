"""Unit tests: two reference programs per class (one with a misleading docstring naming another algorithm)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from classify import classify_text, parse_list_names  # noqa: E402

F = "```python\n{}\n```"

GRAPH = {
    "BFS": [
        '''from collections import deque
def bfs(graph, start, goal):
    queue = deque([[start]])
    visited = {start}
    while queue:
        path = queue.popleft()
        node = path[-1]
        if node == goal:
            return path
        for nb in graph[node]:
            if nb not in visited:
                visited.add(nb)
                queue.append(path + [nb])
    return None''',
        '''def find_path(graph, s, t):
    """Dijkstra's algorithm with a priority queue (heapq)."""
    # uses Dijkstra
    parent = {s: None}
    q = [s]
    while q:
        u = q.pop(0)
        if u == t:
            break
        for v in graph.get(u, []):
            if v not in parent:
                parent[v] = u
                q.append(v)
    if t not in parent:
        return None
    path = []
    while t is not None:
        path.append(t); t = parent[t]
    return path[::-1]'''],
    "DFS": [
        '''def dfs(graph, start, goal, visited=None, path=None):
    if visited is None:
        visited = set(); path = []
    visited.add(start); path = path + [start]
    if start == goal:
        return path
    for nb in graph[start]:
        if nb not in visited:
            r = dfs(graph, nb, goal, visited, path)
            if r:
                return r
    return None''',
        '''def search(graph, start, goal):
    """Breadth-first search (BFS) using a queue."""
    stack = [(start, [start])]
    seen = set()
    while stack:
        node, path = stack.pop()
        if node == goal:
            return path
        if node in seen:
            continue
        seen.add(node)
        for nb in graph[node]:
            stack.append((nb, path + [nb]))
    return None'''],
    "IDDFS": [
        '''def dls(graph, node, goal, depth, path):
    if node == goal:
        return path
    if depth == 0:
        return None
    for nb in graph[node]:
        if nb not in path:
            r = dls(graph, nb, goal, depth - 1, path + [nb])
            if r:
                return r
    return None

def iddfs(graph, start, goal, max_depth=50):
    for depth in range(max_depth):
        r = dls(graph, start, goal, depth, [start])
        if r:
            return r
    return None''',
        '''def path_search(graph, start, goal):
    """A* search."""
    def limited(node, limit, visited):
        if node == goal:
            return [node]
        if limit <= 0:
            return None
        for n in graph[node]:
            if n not in visited:
                sub = limited(n, limit - 1, visited | {n})
                if sub:
                    return [node] + sub
        return None
    for limit in range(len(graph) + 1):
        res = limited(start, limit, {start})
        if res:
            return res
    return None'''],
    "Dijkstra": [
        '''import heapq
def dijkstra(graph, start, goal):
    dist = {start: 0}
    prev = {}
    pq = [(0, start)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == goal:
            break
        if d > dist.get(u, float('inf')):
            continue
        for v, w in graph[u].items():
            nd = d + w
            if nd < dist.get(v, float('inf')):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if goal not in dist:
        return None
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    return dist[goal], path[::-1]''',
        '''import heapq
def heuristic(a, b):
    return 0
def a_star(graph, start, goal):
    """A* search with an admissible heuristic (Bellman-Ford fallback)."""
    open_set = [(0, start)]
    g_score = {start: 0}
    came_from = {}
    while open_set:
        _, cur = heapq.heappop(open_set)
        if cur == goal:
            path = [cur]
            while cur in came_from:
                cur = came_from[cur]; path.append(cur)
            return path[::-1]
        for nb, w in graph[cur].items():
            tentative = g_score[cur] + w
            if tentative < g_score.get(nb, float('inf')):
                came_from[nb] = cur
                g_score[nb] = tentative
                heapq.heappush(open_set, (tentative + heuristic(nb, goal), nb))
    return None''',
        '''def uniform_cost_search(graph, start, goal):
    from queue import PriorityQueue
    pq = PriorityQueue()
    pq.put((0, start, [start]))
    visited = set()
    while not pq.empty():
        cost, node, path = pq.get()
        if node == goal:
            return cost, path
        if node in visited:
            continue
        visited.add(node)
        for nb, weight in graph[node]:
            if nb not in visited:
                pq.put((cost + weight, nb, path + [nb]))
    return None'''],
    "A_star": [
        '''import heapq
def heuristic(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])
def astar(grid, start, goal):
    rows, cols = len(grid), len(grid[0])
    open_heap = [(heuristic(start, goal), 0, start)]
    g_score = {start: 0}
    came_from = {}
    while open_heap:
        f, g, cur = heapq.heappop(open_heap)
        if cur == goal:
            path = [cur]
            while cur in came_from:
                cur = came_from[cur]; path.append(cur)
            return path[::-1]
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nb = (cur[0]+dx, cur[1]+dy)
            if 0 <= nb[0] < rows and 0 <= nb[1] < cols and grid[nb[0]][nb[1]] == 0:
                t = g + 1
                if t < g_score.get(nb, float('inf')):
                    g_score[nb] = t
                    came_from[nb] = cur
                    heapq.heappush(open_heap, (t + heuristic(nb, goal), t, nb))
    return None''',
        '''import heapq, math
class Graph:
    def __init__(self, coords):
        self.coords = coords
        self.edges = {}
    def h(self, a, b):
        (x1, y1), (x2, y2) = self.coords[a], self.coords[b]
        return math.sqrt((x1-x2)**2 + (y1-y2)**2)
    def find(self, s, t):
        """Dijkstra-style search."""
        pq = [(self.h(s, t), s)]
        cost_so_far = {s: 0}
        parent = {s: None}
        while pq:
            _, u = heapq.heappop(pq)
            if u == t:
                break
            for v, w in self.edges.get(u, []):
                new_cost = cost_so_far[u] + w
                if v not in cost_so_far or new_cost < cost_so_far[v]:
                    cost_so_far[v] = new_cost
                    parent[v] = u
                    heapq.heappush(pq, (new_cost + self.h(v, t), v))
        return parent'''],
    "Greedy_best_first": [
        '''import heapq
def heuristic(a, b):
    return abs(a[0]-b[0]) + abs(a[1]-b[1])
def greedy(graph, start, goal):
    pq = [(heuristic(start, goal), start)]
    came_from = {start: None}
    while pq:
        _, cur = heapq.heappop(pq)
        if cur == goal:
            break
        for nb in graph[cur]:
            if nb not in came_from:
                came_from[nb] = cur
                heapq.heappush(pq, (heuristic(nb, goal), nb))
    return came_from''',
        '''import heapq
def manhattan(p, q):
    return abs(p[0]-q[0]) + abs(p[1]-q[1])
def best_first(graph, start, goal):
    """A* algorithm."""
    frontier = [(manhattan(start, goal), start, [start])]
    visited = set()
    while frontier:
        _, node, path = heapq.heappop(frontier)
        if node == goal:
            return path
        visited.add(node)
        for nb in graph[node]:
            if nb not in visited:
                heapq.heappush(frontier, (manhattan(nb, goal), nb, path + [nb]))
    return None'''],
    "Bidirectional": [
        '''from collections import deque
def bidirectional_search(graph, start, goal):
    if start == goal:
        return [start]
    q_f, q_b = deque([start]), deque([goal])
    parents_f, parents_b = {start: None}, {goal: None}
    while q_f and q_b:
        u = q_f.popleft()
        for v in graph[u]:
            if v not in parents_f:
                parents_f[v] = u; q_f.append(v)
                if v in parents_b:
                    return _join(parents_f, parents_b, v)
        u = q_b.popleft()
        for v in graph[u]:
            if v not in parents_b:
                parents_b[v] = u; q_b.append(v)
                if v in parents_f:
                    return _join(parents_f, parents_b, v)
    return None
def _join(pf, pb, m):
    path = []
    n = m
    while n is not None:
        path.append(n); n = pf[n]
    path.reverse()
    n = pb[m]
    while n is not None:
        path.append(n); n = pb[n]
    return path''',
        '''from collections import deque
def search(graph, s, t):
    """Plain BFS."""
    visited_start = {s}; visited_end = {t}
    frontier_s = deque([s]); frontier_t = deque([t])
    while frontier_s and frontier_t:
        a = frontier_s.popleft()
        for n in graph[a]:
            if n in visited_end:
                return True
            if n not in visited_start:
                visited_start.add(n); frontier_s.append(n)
        b = frontier_t.popleft()
        for n in graph[b]:
            if n in visited_start:
                return True
            if n not in visited_end:
                visited_end.add(n); frontier_t.append(n)
    return False'''],
    "Bellman_Ford": [
        '''def bellman_ford(graph, source):
    dist = {v: float('inf') for v in graph}
    dist[source] = 0
    for _ in range(len(graph) - 1):
        for u in graph:
            for v, w in graph[u].items():
                if dist[u] + w < dist[v]:
                    dist[v] = dist[u] + w
    for u in graph:
        for v, w in graph[u].items():
            if dist[u] + w < dist[v]:
                raise ValueError("negative cycle")
    return dist''',
        '''def shortest(edges, n, src):
    """Dijkstra's algorithm."""
    d = [float('inf')] * n
    d[src] = 0
    for i in range(n - 1):
        for u, v, w in edges:
            if d[u] != float('inf') and d[u] + w < d[v]:
                d[v] = d[u] + w
    return d'''],
    "SPFA": [
        '''from collections import deque
def spfa(graph, src):
    dist = {v: float('inf') for v in graph}
    dist[src] = 0
    in_queue = {src}
    q = deque([src])
    while q:
        u = q.popleft()
        in_queue.discard(u)
        for v, w in graph[u]:
            if dist[u] + w < dist[v]:
                dist[v] = dist[u] + w
                if v not in in_queue:
                    q.append(v); in_queue.add(v)
    return dist''',
        '''from collections import deque
def shortest_path(graph, s):
    """BFS-based breadth first search."""
    distance = {s: 0}
    queue = deque([s])
    while queue:
        u = queue.popleft()
        for v, cost in graph[u].items():
            new_dist = distance[u] + cost
            if new_dist < distance.get(v, float('inf')):
                distance[v] = new_dist
                queue.append(v)
    return distance'''],
    "Floyd_Warshall": [
        '''def floyd_warshall(n, edges):
    INF = float('inf')
    dist = [[INF]*n for _ in range(n)]
    for i in range(n):
        dist[i][i] = 0
    for u, v, w in edges:
        dist[u][v] = w
    for k in range(n):
        for i in range(n):
            for j in range(n):
                if dist[i][k] + dist[k][j] < dist[i][j]:
                    dist[i][j] = dist[i][k] + dist[k][j]
    return dist''',
        '''def all_pairs(m):
    """Dijkstra from every node."""
    n = len(m)
    d = [row[:] for row in m]
    for via in range(n):
        for a in range(n):
            for b in range(n):
                d[a][b] = min(d[a][b], d[a][via] + d[via][b])
    return d'''],
}

SORT = {
    "Quick": [
        '''def quicksort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    mid = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left) + mid + quicksort(right)''',
        '''def partition(a, lo, hi):
    """Merge sort helper."""
    p = a[hi]
    i = lo - 1
    for j in range(lo, hi):
        if a[j] <= p:
            i += 1
            a[i], a[j] = a[j], a[i]
    a[i + 1], a[hi] = a[hi], a[i + 1]
    return i + 1
def sort(a, lo=0, hi=None):
    if hi is None:
        hi = len(a) - 1
    if lo < hi:
        q = partition(a, lo, hi)
        sort(a, lo, q - 1)
        sort(a, q + 1, hi)
    return a'''],
    "Merge": [
        '''def merge_sort(arr):
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    return merge(left, right)
def merge(left, right):
    out = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            out.append(left[i]); i += 1
        else:
            out.append(right[j]); j += 1
    out.extend(left[i:]); out.extend(right[j:])
    return out''',
        '''def sort_list(a):
    """Quicksort implementation with pivot."""
    if len(a) < 2:
        return a
    m = len(a) // 2
    l, r = sort_list(a[:m]), sort_list(a[m:])
    res = []
    while l and r:
        res.append(l.pop(0) if l[0] <= r[0] else r.pop(0))
    return res + l + r'''],
    "Heap": [
        '''def heapify(arr, n, i):
    largest = i
    l, r = 2 * i + 1, 2 * i + 2
    if l < n and arr[l] > arr[largest]:
        largest = l
    if r < n and arr[r] > arr[largest]:
        largest = r
    if largest != i:
        arr[i], arr[largest] = arr[largest], arr[i]
        heapify(arr, n, largest)
def heap_sort(arr):
    n = len(arr)
    for i in range(n // 2 - 1, -1, -1):
        heapify(arr, n, i)
    for i in range(n - 1, 0, -1):
        arr[0], arr[i] = arr[i], arr[0]
        heapify(arr, i, 0)
    return arr''',
        '''import heapq
def my_sort(xs):
    """Bubble sort."""
    h = list(xs)
    heapq.heapify(h)
    return [heapq.heappop(h) for _ in range(len(h))]'''],
    "Insertion": [
        '''def insertion_sort(arr):
    for i in range(1, len(arr)):
        key = arr[i]
        j = i - 1
        while j >= 0 and arr[j] > key:
            arr[j + 1] = arr[j]
            j -= 1
        arr[j + 1] = key
    return arr''',
        '''def sort(a):
    """Selection sort algorithm."""
    for i in range(1, len(a)):
        k = i
        while k > 0 and a[k - 1] > a[k]:
            a[k - 1], a[k] = a[k], a[k - 1]
            k -= 1
    return a'''],
    "Selection": [
        '''def selection_sort(arr):
    n = len(arr)
    for i in range(n):
        min_idx = i
        for j in range(i + 1, n):
            if arr[j] < arr[min_idx]:
                min_idx = j
        arr[i], arr[min_idx] = arr[min_idx], arr[i]
    return arr''',
        '''def sort(a):
    """Insertion sort."""
    for i in range(len(a)):
        smallest = i
        for j in range(i + 1, len(a)):
            if a[j] < a[smallest]:
                smallest = j
        a[i], a[smallest] = a[smallest], a[i]
    return a'''],
    "Bubble": [
        '''def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        swapped = False
        for j in range(0, n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                swapped = True
        if not swapped:
            break
    return arr''',
        '''def sort(a):
    """Quick sort."""
    for i in range(len(a)):
        for j in range(len(a) - 1 - i):
            if a[j] > a[j + 1]:
                a[j], a[j + 1] = a[j + 1], a[j]
    return a'''],
    "Shell": [
        '''def shell_sort(arr):
    n = len(arr)
    gap = n // 2
    while gap > 0:
        for i in range(gap, n):
            temp = arr[i]
            j = i
            while j >= gap and arr[j - gap] > temp:
                arr[j] = arr[j - gap]
                j -= gap
            arr[j] = temp
        gap //= 2
    return arr''',
        '''def sort(a):
    """Insertion sort variant."""
    interval = len(a) // 2
    while interval > 0:
        for i in range(interval, len(a)):
            t = a[i]; j = i
            while j >= interval and a[j - interval] > t:
                a[j] = a[j - interval]; j -= interval
            a[j] = t
        interval //= 2
    return a'''],
    "Counting": [
        '''def counting_sort(arr):
    if not arr:
        return arr
    lo, hi = min(arr), max(arr)
    count = [0] * (hi - lo + 1)
    for x in arr:
        count[x - lo] += 1
    out = []
    for i, c in enumerate(count):
        out.extend([i + lo] * c)
    return out''',
        '''def sort(a):
    """Radix sort."""
    if not a:
        return []
    m = min(a)
    counts = [0] * (max(a) - m + 1)
    for v in a:
        counts[v - m] += 1
    res = []
    for i in range(len(counts)):
        res += [i + m] * counts[i]
    return res'''],
    "Radix": [
        '''def counting_sort_exp(arr, exp):
    n = len(arr)
    out = [0] * n
    count = [0] * 10
    for x in arr:
        count[(x // exp) % 10] += 1
    for i in range(1, 10):
        count[i] += count[i - 1]
    for x in reversed(arr):
        idx = (x // exp) % 10
        out[count[idx] - 1] = x
        count[idx] -= 1
    return out
def radix_sort(arr):
    if not arr:
        return arr
    m = max(arr)
    exp = 1
    while m // exp > 0:
        arr = counting_sort_exp(arr, exp)
        exp *= 10
    return arr''',
        '''def sort(a):
    """Counting sort."""
    place = 1
    while a and max(a) // place > 0:
        bins = [[] for _ in range(10)]
        for v in a:
            bins[(v // place) % 10].append(v)
        a = [v for b in bins for v in b]
        place *= 10
    return a'''],
    "Bucket": [
        '''def bucket_sort(arr):
    if not arr:
        return arr
    lo, hi = min(arr), max(arr)
    n = len(arr)
    buckets = [[] for _ in range(n)]
    for x in arr:
        idx = int((x - lo) / (hi - lo + 1) * n)
        buckets[idx].append(x)
    out = []
    for b in buckets:
        out.extend(sorted(b))
    return out''',
        '''def insertion(b):
    for i in range(1, len(b)):
        key = b[i]; j = i - 1
        while j >= 0 and b[j] > key:
            b[j + 1] = b[j]; j -= 1
        b[j + 1] = key
    return b
def sort(a, k=5):
    """Insertion sort."""
    if not a:
        return a
    lo, hi = min(a), max(a)
    width = (hi - lo) / k + 1
    bucket_list = [[] for _ in range(k)]
    for v in a:
        bucket_list[int((v - lo) / width)].append(v)
    return [v for bl in bucket_list for v in insertion(bl)]'''],
    "Tim_hybrid": [
        '''MIN_RUN = 32
def insertion_sort(a, l, r):
    for i in range(l + 1, r + 1):
        key = a[i]; j = i - 1
        while j >= l and a[j] > key:
            a[j + 1] = a[j]; j -= 1
        a[j + 1] = key
def merge(a, l, m, r):
    left, right = a[l:m + 1], a[m + 1:r + 1]
    i = j = 0; k = l
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            a[k] = left[i]; i += 1
        else:
            a[k] = right[j]; j += 1
        k += 1
    while i < len(left):
        a[k] = left[i]; i += 1; k += 1
    while j < len(right):
        a[k] = right[j]; j += 1; k += 1
def tim_sort(a):
    n = len(a)
    for s in range(0, n, MIN_RUN):
        insertion_sort(a, s, min(s + MIN_RUN - 1, n - 1))
    size = MIN_RUN
    while size < n:
        for l in range(0, n, 2 * size):
            m = min(n - 1, l + size - 1); r = min(n - 1, l + 2 * size - 1)
            if m < r:
                merge(a, l, m, r)
        size *= 2
    return a''',
        '''def hybrid(a, minrun=16):
    """Bubble sort."""
    runs = []
    for s in range(0, len(a), minrun):
        chunk = a[s:s + minrun]
        for i in range(1, len(chunk)):
            key = chunk[i]; j = i - 1
            while j >= 0 and chunk[j] > key:
                chunk[j + 1] = chunk[j]; j -= 1
            chunk[j + 1] = key
        runs.append(chunk)
    import heapq as _h
    return list(_h.merge(*runs))'''],
    "Builtin": [
        '''def sort_numbers(xs):
    return sorted(xs)''',
        '''def sort(a):
    """Quicksort implementation."""
    a.sort()
    return a'''],
}


def check(table: dict, kind: str) -> list[str]:
    fails = []
    for cls, progs in table.items():
        for i, p in enumerate(progs):
            r = classify_text("Here is code:\n" + F.format(p) + "\nDone.", kind)
            if r["label"] != cls:
                fails.append(f"{kind}:{cls}[{i}] -> {r['label']} raw={r['raw_labels']}")
    return fails


def test_graph() -> None:
    fails = check(GRAPH, "graph")
    assert not fails, "\n".join(fails)


def test_sort() -> None:
    fails = check(SORT, "sort")
    assert not fails, "\n".join(fails)


def test_unparseable_and_list() -> None:
    assert classify_text("I cannot help with that.", "graph")["label"] == "Unparseable"
    lst = "1. Dijkstra's Algorithm\n2. A* Search\n3. Breadth-First Search\n4. Johnson's algorithm"
    assert parse_list_names(lst, "graph") == ["Dijkstra", "A_star", "BFS", "Other"]


if __name__ == "__main__":
    f = check(GRAPH, "graph") + check(SORT, "sort")
    print("\n".join(f) if f else "ALL PASS")
    print(f"{sum(len(v) for v in GRAPH.values()) + sum(len(v) for v in SORT.values())} programs, {len(f)} failures")
