import heapq
def heuristic(a, b):
    return abs(a - b)
def find_path(graph, start, goal):
    pq = [(heuristic(start, goal), start)]; parent = {start: None}
    while pq:
        _, u = heapq.heappop(pq)
        if u == goal:
            p = [u]
            while parent[p[-1]] is not None:
                p.append(parent[p[-1]])
            return p[::-1]
        for v in graph[u]:
            if v not in parent:
                parent[v] = u
                heapq.heappush(pq, (heuristic(v, goal), v))
    return None
