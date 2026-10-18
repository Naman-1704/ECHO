from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db
from app.dependencies import get_current_user
from app.graph.builder import ensure_graph, rebuild_graph
from app.graph.insights import attention_report, key_people, timeline
from app.graph.queries import get_graph_view, get_node_detail

router = APIRouter(tags=["graph"])

_TYPES = {"person", "project", "decision", "action"}


@router.get("/graph/network")
def network(
    types: str = Query("person,project", description="comma-separated: person,project,decision,action"),
    min_weight: int = Query(1, ge=1, le=50),
    hide_owner: bool = False,
    limit: int = Query(80, ge=5, le=300),
    focus: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chosen = tuple(t for t in (x.strip() for x in types.split(",")) if t in _TYPES) or ("person", "project")
    if not ensure_graph(db, user):
        return {"nodes": [], "edges": [], "stats": {"total_nodes": 0, "total_edges": 0, "shown_nodes": 0,
                                                    "shown_edges": 0, "hidden_isolated": 0}}
    return get_graph_view(db, user.id, types=chosen, min_weight=min_weight, hide_owner=hide_owner,
                          limit=limit, focus_id=focus)


@router.get("/graph/node/{node_id}")
def node_detail(node_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    detail = get_node_detail(db, user.id, node_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return detail


@router.post("/graph/rebuild")
def rebuild(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Re-derives the graph from stored extractions (no model calls, takes seconds)."""
    return rebuild_graph(db, user)


@router.get("/insights/attention")
def attention(
    stale_days: int = Query(14, ge=1, le=365),
    dormant_days: int = Query(60, ge=1, le=730),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_graph(db, user)
    return attention_report(db, user.id, stale_days=stale_days, dormant_days=dormant_days)


@router.get("/insights/key-people")
def people(limit: int = Query(6, ge=1, le=20), user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    ensure_graph(db, user)
    return key_people(db, user.id, limit=limit)


@router.get("/insights/timeline")
def events(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_graph(db, user)
    return timeline(db, user.id)
