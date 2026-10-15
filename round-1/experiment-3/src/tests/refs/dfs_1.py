def find_path(graph, start, goal):
    stack = [(start, [start])]
    visited = set()
    while stack:
        node, path = stack.pop()
        if node == goal:
            return path
        if node in visited:
            continue
        visited.add(node)
        for n in graph.get(node, []):
            if n not in visited:
                stack.append((n, path + [n]))
    return None
