def shortest_path(graph, source, target):
    nodes = list(graph); INF = float("inf")
    dist = {i: {j: INF for j in nodes} for i in nodes}; nxt = {i: {j: None for j in nodes} for i in nodes}
    for i in nodes:
        dist[i][i] = 0; nxt[i][i] = i
        for j, w in graph[i]:
            if w < dist[i][j]:
                dist[i][j] = w; nxt[i][j] = j
    for k in nodes:
        for i in nodes:
            for j in nodes:
                if dist[i][k] + dist[k][j] < dist[i][j]:
                    dist[i][j] = dist[i][k] + dist[k][j]; nxt[i][j] = nxt[i][k]
    if dist[source][target] == INF:
        return INF, None
    p = [source]
    while p[-1] != target:
        p.append(nxt[p[-1]][target])
    return dist[source][target], p
