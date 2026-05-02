from __future__ import annotations

import math
from collections import defaultdict, deque

from .models import CanvasBoard


def _layered(board: CanvasBoard) -> CanvasBoard:
    indeg: dict[str, int] = {n.node_id: 0 for n in board.nodes}
    out: dict[str, list[str]] = defaultdict(list)
    for e in board.edges:
        if e.source_id in indeg and e.target_id in indeg:
            indeg[e.target_id] += 1
            out[e.source_id].append(e.target_id)

    layer: dict[str, int] = {nid: 0 for nid in indeg}
    q = deque([nid for nid, d in indeg.items() if d == 0])
    visited: set[str] = set(q)
    while q:
        u = q.popleft()
        for v in out[u]:
            layer[v] = max(layer[v], layer[u] + 1)
            if v not in visited:
                visited.add(v)
                q.append(v)

    by_layer: dict[int, list[str]] = defaultdict(list)
    for nid, l in layer.items():
        by_layer[l].append(nid)

    nodes_by_id = {n.node_id: n for n in board.nodes}
    for l, ids in by_layer.items():
        ids.sort()
        cnt = len(ids)
        for i, nid in enumerate(ids):
            n = nodes_by_id[nid]
            n.x = l * 240.0
            n.y = (i - (cnt - 1) / 2.0) * 120.0
    return board


def _radial(board: CanvasBoard) -> CanvasBoard:
    if not board.nodes:
        return board
    deg: dict[str, int] = defaultdict(int)
    for e in board.edges:
        deg[e.source_id] += 1
        deg[e.target_id] += 1
    center_id = max(board.nodes, key=lambda n: deg[n.node_id]).node_id
    others = [n for n in board.nodes if n.node_id != center_id]
    for n in board.nodes:
        if n.node_id == center_id:
            n.x, n.y = 0.0, 0.0
    radius = 260.0
    cnt = max(1, len(others))
    for i, n in enumerate(others):
        theta = 2 * math.pi * i / cnt
        n.x = round(radius * math.cos(theta), 2)
        n.y = round(radius * math.sin(theta), 2)
    return board


def auto_layout(board: CanvasBoard, algorithm: str = "layered") -> CanvasBoard:
    if algorithm == "radial":
        return _radial(board)
    return _layered(board)
