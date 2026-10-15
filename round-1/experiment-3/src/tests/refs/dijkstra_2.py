def shortest_path(graph, source, target):
    dist = {n: float("inf") for n in graph}; dist[source] = 0
    prev = {}; unvisited = set(graph)
    while unvisited:
        u = min(unvisited, key=lambda n: dist[n])
        if dist[u] == float("inf"):
            break
        unvisited.remove(u)
        if u == target:
            break
        for v, w in graph[u]:
            if dist[u] + w < dist[v]:
                dist[v] = dist[u] + w; prev[v] = u
    if dist[target] == float("inf"):
        return float("inf"), None
    p = [target]
    while p[-1] != source:
        p.append(prev[p[-1]])
    return dist[target], p[::-1]
