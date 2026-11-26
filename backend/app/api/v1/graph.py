"""Graph routes (Phase 5A): filtered graph views, node detail, neighborhood.

All responses come from stored analysis records; dependency edges always carry
source evidence and ``CONTAINS`` stays structural (never a dependency).
"""

import logging

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user, get_graph_bundle

logger = logging.getLogger("flowlens.graph_routes")

router = APIRouter(prefix="/api/v1", tags=["graph"])


@router.get("/analyses/{analysis_id}/graph")
def get_graph(
    analysis_id: str,
    view: str = Query("function", pattern="^(module|class|function)$"),
    node_kinds: list[str] | None = Query(None),
    edge_kinds: list[str] | None = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    user=Depends(get_current_user),
    bundle=Depends(get_graph_bundle),
):
    """Bounded, filtered subgraph. `truncated` reports server-side limits."""
    return bundle.service.graph(
        user,
        analysis_id,
        view=view,
        node_kinds=list(node_kinds or []),
        edge_kinds=list(edge_kinds or []),
        limit=limit,
    )


@router.get("/analyses/{analysis_id}/nodes/{node_id}")
def get_node(
    analysis_id: str,
    node_id: str,
    user=Depends(get_current_user),
    bundle=Depends(get_graph_bundle),
):
    """Node detail (kind, location, metrics, coverage status)."""
    return bundle.service.node(user, analysis_id, node_id)


@router.get("/analyses/{analysis_id}/nodes/{node_id}/neighbors")
def get_node_neighbors(
    analysis_id: str,
    node_id: str,
    depth: int = Query(1, ge=1, le=3),
    direction: str = Query("both", pattern="^(upstream|downstream|both)$"),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(get_current_user),
    bundle=Depends(get_graph_bundle),
):
    """Bounded neighborhood expansion at symbol granularity."""
    return bundle.service.neighbors(
        user,
        analysis_id,
        node_id,
        depth=depth,
        direction=direction,
        limit=limit,
    )
