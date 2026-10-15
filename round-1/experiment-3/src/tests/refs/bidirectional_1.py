from collections import deque
def find_path(graph, start, goal):
    if start == goal:
        return [start]
    rev = {}
    for u, vs in graph.items():
        for v in vs:
            rev.setdefault(v, []).append(u)
    fwd_parent = {start: None}; bwd_parent = {goal: None}
    fq = deque([start]); bq = deque([goal])
    while fq and bq:
        u = fq.popleft()
        for v in graph.get(u, []):
            if v not in fwd_parent:
                fwd_parent[v] = u; fq.append(v)
                if v in bwd_parent:
                    return _join(v, fwd_parent, bwd_parent)
        u = bq.popleft()
        for v in rev.get(u, []):
            if v not in bwd_parent:
                bwd_parent[v] = u; bq.append(v)
                if v in fwd_parent:
                    return _join(v, fwd_parent, bwd_parent)
    return None
def _join(m, fp, bp):
    a = []; x = m
    while x is not None:
        a.append(x); x = fp[x]
    a.reverse(); x = bp[m]
    while x is not None:
        a.append(x); x = bp[x]
    return a
