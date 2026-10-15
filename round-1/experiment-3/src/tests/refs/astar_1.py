import heapq
def heuristic(a, b):
    return 0
def shortest_path(graph, source, target):
    g_score = {source: 0}; prev = {}
    open_set = [(heuristic(source, target), source)]
    while open_set:
        f, u = heapq.heappop(open_set)
        if u == target:
            p = [u]
            while p[-1] in prev:
                p.append(prev[p[-1]])
            return g_score[u], p[::-1]
        for v, w in graph[u]:
            t = g_score[u] + w
            if t < g_score.get(v, float("inf")):
                g_score[v] = t; prev[v] = u
                heapq.heappush(open_set, (t + heuristic(v, target), v))
    return float("inf"), None
