def find_path(graph, start, goal):
    def dls(node, depth, path):
        if node == goal:
            return path
        if depth == 0:
            return None
        for n in graph.get(node, []):
            if n not in path:
                r = dls(n, depth - 1, path + [n])
                if r:
                    return r
        return None
    for depth in range(len(graph) + 1):
        r = dls(start, depth, [start])
        if r:
            return r
    return None
