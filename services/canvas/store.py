from __future__ import annotations

import uuid
from datetime import datetime

from .models import (
    CanvasBoard,
    CanvasEdge,
    CanvasNode,
    CanvasNodeKind,
    UpsertEdgeRequest,
    UpsertNodeRequest,
)


_BOARDS: dict[str, CanvasBoard] = {}


def _now(b: CanvasBoard) -> None:
    b.updated_at = datetime.utcnow()


def _seed_xia_dynasty() -> CanvasBoard:
    board_id = f"board_{uuid.uuid4().hex[:10]}"
    nodes = [
        CanvasNode(node_id="n_yu", kind=CanvasNodeKind.FIGURE, label="大禹", detail="夏朝奠基者，治水功成", period="夏·约公元前 2070", x=0, y=0),
        CanvasNode(node_id="n_gun", kind=CanvasNodeKind.FIGURE, label="鲧", detail="禹之父，堵法治水九年不成", period="尧舜时期", x=-260, y=-120),
        CanvasNode(node_id="n_flood", kind=CanvasNodeKind.EVENT, label="洪水之患", detail="黄河流域大洪水，民不聊生", period="尧舜时期", x=-260, y=120),
        CanvasNode(node_id="n_shudao", kind=CanvasNodeKind.POLICY, label="疏导之策", detail="改父之堵为疏，分九河注海", period="禹治水期", x=260, y=-120),
        CanvasNode(node_id="n_jiuzhou", kind=CanvasNodeKind.POLICY, label="划分九州", detail="按地理与贡赋划分九州", period="禹治水末期", x=260, y=120),
        CanvasNode(node_id="n_xia", kind=CanvasNodeKind.EVENT, label="开夏立国", detail="禹受禅，启继位，世袭制始", period="约公元前 2070", x=520, y=0),
    ]
    edges = [
        CanvasEdge(edge_id="e1", source_id="n_flood", target_id="n_gun", label="引出"),
        CanvasEdge(edge_id="e2", source_id="n_gun", target_id="n_yu", label="父子相承"),
        CanvasEdge(edge_id="e3", source_id="n_flood", target_id="n_yu", label="承命治水"),
        CanvasEdge(edge_id="e4", source_id="n_yu", target_id="n_shudao", label="改弦"),
        CanvasEdge(edge_id="e5", source_id="n_shudao", target_id="n_jiuzhou", label="水定土分"),
        CanvasEdge(edge_id="e6", source_id="n_jiuzhou", target_id="n_xia", label="奠基"),
    ]
    board = CanvasBoard(
        board_id=board_id,
        title="大禹治水 · 夏代奠基知识谱系",
        summary="以治水为主线，串联人物—事件—政策—地理四类节点，呈现夏代奠基的因果脉络。",
        nodes=nodes,
        edges=edges,
    )
    _BOARDS[board_id] = board
    return board


def list_boards() -> list[CanvasBoard]:
    return list(_BOARDS.values())


def get_board(board_id: str) -> CanvasBoard | None:
    return _BOARDS.get(board_id)


def create_board(title: str, summary: str = "", seed: bool = False) -> CanvasBoard:
    if seed:
        b = _seed_xia_dynasty()
        b.title = title
        if summary:
            b.summary = summary
        _now(b)
        return b
    board_id = f"board_{uuid.uuid4().hex[:10]}"
    b = CanvasBoard(board_id=board_id, title=title, summary=summary)
    _BOARDS[board_id] = b
    return b


def delete_board(board_id: str) -> bool:
    return _BOARDS.pop(board_id, None) is not None


def upsert_node(board_id: str, payload: UpsertNodeRequest) -> CanvasNode | None:
    b = _BOARDS.get(board_id)
    if b is None:
        return None
    if payload.node_id:
        for n in b.nodes:
            if n.node_id == payload.node_id:
                n.kind = payload.kind
                n.label = payload.label
                n.detail = payload.detail
                n.period = payload.period
                n.x = payload.x
                n.y = payload.y
                _now(b)
                return n
    node = CanvasNode(
        node_id=payload.node_id or f"n_{uuid.uuid4().hex[:8]}",
        kind=payload.kind,
        label=payload.label,
        detail=payload.detail,
        period=payload.period,
        x=payload.x,
        y=payload.y,
    )
    b.nodes.append(node)
    _now(b)
    return node


def delete_node(board_id: str, node_id: str) -> bool:
    b = _BOARDS.get(board_id)
    if b is None:
        return False
    before = len(b.nodes)
    b.nodes = [n for n in b.nodes if n.node_id != node_id]
    b.edges = [e for e in b.edges if e.source_id != node_id and e.target_id != node_id]
    if len(b.nodes) != before:
        _now(b)
        return True
    return False


def upsert_edge(board_id: str, payload: UpsertEdgeRequest) -> CanvasEdge | None:
    b = _BOARDS.get(board_id)
    if b is None:
        return None
    ids = {n.node_id for n in b.nodes}
    if payload.source_id not in ids or payload.target_id not in ids:
        return None
    if payload.edge_id:
        for e in b.edges:
            if e.edge_id == payload.edge_id:
                e.source_id = payload.source_id
                e.target_id = payload.target_id
                e.label = payload.label
                _now(b)
                return e
    edge = CanvasEdge(
        edge_id=payload.edge_id or f"e_{uuid.uuid4().hex[:8]}",
        source_id=payload.source_id,
        target_id=payload.target_id,
        label=payload.label,
    )
    b.edges.append(edge)
    _now(b)
    return edge


def delete_edge(board_id: str, edge_id: str) -> bool:
    b = _BOARDS.get(board_id)
    if b is None:
        return False
    before = len(b.edges)
    b.edges = [e for e in b.edges if e.edge_id != edge_id]
    if len(b.edges) != before:
        _now(b)
        return True
    return False
