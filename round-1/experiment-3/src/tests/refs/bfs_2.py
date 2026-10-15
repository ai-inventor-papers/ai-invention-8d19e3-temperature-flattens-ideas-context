def find_path(graph, start, goal):
    queue = [[start]]
    seen = {start}
    while queue:
        path = queue.pop(0)
        node = path[-1]
        if node == goal:
            return path
        for n in graph[node]:
            if n not in seen:
                seen.add(n); queue.append(path + [n])
    return None
