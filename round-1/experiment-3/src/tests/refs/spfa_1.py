from collections import deque
def shortest_path(graph, source, target):
    dist = {n: float("inf") for n in graph}; dist[source] = 0; prev = {}
    q = deque([source]); in_queue = {source}
    while q:
        u = q.popleft(); in_queue.discard(u)
        for v, w in graph[u]:
            if dist[u] + w < dist[v]:
                dist[v] = dist[u] + w; prev[v] = u
                if v not in in_queue:
                    q.append(v); in_queue.add(v)
    if dist[target] == float("inf"):
        return float("inf"), None
    p = [target]
    while p[-1] != source:
        p.append(prev[p[-1]])
    return dist[target], p[::-1]
