def shortest_path(graph, source, target):
    dist = {n: float("inf") for n in graph}; dist[source] = 0; prev = {}
    for _ in range(len(graph) - 1):
        for u in graph:
            for v, w in graph[u]:
                if dist[u] + w < dist[v]:
                    dist[v] = dist[u] + w; prev[v] = u
    if dist[target] == float("inf"):
        return float("inf"), None
    p = [target]
    while p[-1] != source:
        p.append(prev[p[-1]])
    return dist[target], p[::-1]
