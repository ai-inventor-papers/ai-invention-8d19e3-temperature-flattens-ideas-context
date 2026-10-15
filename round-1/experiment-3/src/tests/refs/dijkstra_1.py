import heapq
def shortest_path(graph, source, target):
    dist = {source: 0}; prev = {}
    pq = [(0, source)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == target:
            path = [u]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            return d, path[::-1]
        if d > dist.get(u, float("inf")):
            continue
        for v, w in graph.get(u, []):
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd; prev[v] = u
                heapq.heappush(pq, (nd, v))
    return float("inf"), None
