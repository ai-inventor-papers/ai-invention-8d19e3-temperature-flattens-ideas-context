from collections import deque
def find_path(graph, start, goal):
    """Uses Dijkstra-like idea (docstring mentions Dijkstra and heapq but is BFS)."""
    if start == goal:
        return [start]
    q = deque([start]); parent = {start: None}
    while q:
        u = q.popleft()  # heapq comment
        for v in graph.get(u, []):
            if v not in parent:
                parent[v] = u
                if v == goal:
                    p = [v]
                    while parent[p[-1]] is not None:
                        p.append(parent[p[-1]])
                    return p[::-1]
                q.append(v)
    return None
