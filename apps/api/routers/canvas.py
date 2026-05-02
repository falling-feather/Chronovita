from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from services.canvas import (
    CanvasBoard,
    CanvasEdge,
    CanvasNode,
    CreateBoardRequest,
    ExportFormat,
    LayoutRequest,
    UpsertEdgeRequest,
    UpsertNodeRequest,
    auto_layout,
    create_board,
    delete_board,
    delete_edge,
    delete_node,
    export_board,
    get_board,
    list_boards,
    upsert_edge,
    upsert_node,
)

router = APIRouter()


@router.get("/boards", response_model=list[CanvasBoard], summary="谱系列表")
async def fetch_boards() -> list[CanvasBoard]:
    return list_boards()


@router.post("/boards", response_model=CanvasBoard, summary="新建谱系")
async def add_board(payload: CreateBoardRequest) -> CanvasBoard:
    return create_board(payload.title, payload.summary, payload.seed)


@router.get("/boards/{board_id}", response_model=CanvasBoard, summary="谱系详情")
async def fetch_board(board_id: str) -> CanvasBoard:
    b = get_board(board_id)
    if b is None:
        raise HTTPException(status_code=404, detail="谱系不存在")
    return b


@router.delete("/boards/{board_id}", summary="删除谱系")
async def remove_board(board_id: str) -> dict:
    if not delete_board(board_id):
        raise HTTPException(status_code=404, detail="谱系不存在")
    return {"deleted": board_id}


@router.post("/boards/{board_id}/nodes", response_model=CanvasNode, summary="新增/更新节点")
async def upsert_board_node(board_id: str, payload: UpsertNodeRequest) -> CanvasNode:
    n = upsert_node(board_id, payload)
    if n is None:
        raise HTTPException(status_code=404, detail="谱系不存在")
    return n


@router.delete("/boards/{board_id}/nodes/{node_id}", summary="删除节点")
async def remove_node(board_id: str, node_id: str) -> dict:
    if not delete_node(board_id, node_id):
        raise HTTPException(status_code=404, detail="节点不存在")
    return {"deleted": node_id}


@router.post("/boards/{board_id}/edges", response_model=CanvasEdge, summary="新增/更新边")
async def upsert_board_edge(board_id: str, payload: UpsertEdgeRequest) -> CanvasEdge:
    e = upsert_edge(board_id, payload)
    if e is None:
        raise HTTPException(status_code=400, detail="谱系或端点不存在")
    return e


@router.delete("/boards/{board_id}/edges/{edge_id}", summary="删除边")
async def remove_edge(board_id: str, edge_id: str) -> dict:
    if not delete_edge(board_id, edge_id):
        raise HTTPException(status_code=404, detail="边不存在")
    return {"deleted": edge_id}


@router.post("/boards/{board_id}/layout", response_model=CanvasBoard, summary="自动布局")
async def layout_board(board_id: str, payload: LayoutRequest) -> CanvasBoard:
    b = get_board(board_id)
    if b is None:
        raise HTTPException(status_code=404, detail="谱系不存在")
    return auto_layout(b, payload.algorithm)


@router.get("/boards/{board_id}/export", summary="导出谱系")
async def export(
    board_id: str,
    fmt: ExportFormat = Query(ExportFormat.MARKDOWN, alias="format"),
) -> Response:
    b = get_board(board_id)
    if b is None:
        raise HTTPException(status_code=404, detail="谱系不存在")
    body, media_type = export_board(b, fmt)
    suffix = {ExportFormat.JSON: "json", ExportFormat.MARKDOWN: "md", ExportFormat.MERMAID: "mmd"}[fmt]
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{board_id}.{suffix}"'},
    )
