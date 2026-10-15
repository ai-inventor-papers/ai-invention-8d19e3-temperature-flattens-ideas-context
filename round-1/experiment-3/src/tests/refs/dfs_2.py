def find_path(graph, start, goal, visited=None):
    if visited is None:
        visited = set()
    if start == goal:
        return [start]
    visited.add(start)
    for n in graph.get(start, []):
        if n not in visited:
            r = find_path(graph, n, goal, visited)
            if r:
                return [start] + r
    return None
