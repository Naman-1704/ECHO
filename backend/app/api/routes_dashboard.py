from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, GraphNode, RawItem, User
from app.db.session import get_db
from app.dependencies import get_current_user
from app.graph.builder import ensure_graph, is_open
from app.graph.queries import source_info

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _nodes(db: Session, user_id: str, type_: str) -> list[GraphNode]:
    return list(db.execute(select(GraphNode).where(GraphNode.user_id == user_id, GraphNode.type == type_)).scalars())


@router.get("/summary")
def get_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Overview data, read from the knowledge graph so "Priya", "Priya Sharma" and
    "Sharma, Priya" are ONE person (the old per-chunk tally counted them three times).
    The response shape is unchanged, with extra fields (aliases, last_seen, source) that
    the UI uses for links back to the original email or document.
    """
    total_items = db.execute(select(func.count()).select_from(RawItem).where(RawItem.user_id == user.id)).scalar()
    total_chunks = db.execute(select(func.count()).select_from(Chunk).where(Chunk.user_id == user.id)).scalar()
    has_graph = ensure_graph(db, user)

    people = [n for n in _nodes(db, user.id, "person") if not n.is_owner] if has_graph else []
    projects = _nodes(db, user.id, "project") if has_graph else []
    decisions = _nodes(db, user.id, "decision") if has_graph else []
    actions = [a for a in _nodes(db, user.id, "action") if is_open(a.attrs.get("status"))] if has_graph else []

    decisions.sort(key=lambda n: n.first_seen.timestamp() if n.first_seen else 0, reverse=True)
    actions.sort(key=lambda n: n.last_seen.timestamp() if n.last_seen else 0, reverse=True)
    info = source_info(db, [n.attrs.get("chunk_id") for n in decisions[:20] + actions[:20] if n.attrs.get("chunk_id")])

    def entity(n: GraphNode, samples: list[str]) -> dict:
        return {"id": n.id, "name": n.name, "aliases": n.aliases or [], "context_samples": samples[:3],
                "mention_count": n.mention_count, "last_seen": n.last_seen.strftime("%Y-%m-%d") if n.last_seen else None}

    return {
        "stats": {
            "total_emails_ingested": total_items,
            "total_chunks_processed": total_chunks,
            "unique_people": len(people),
            "unique_projects": len(projects),
        },
        "people": [entity(n, (n.attrs or {}).get("roles", [])) for n in
                   sorted(people, key=lambda n: (-n.mention_count, n.name.lower()))],
        "projects": [entity(n, (n.attrs or {}).get("contexts", [])) for n in
                     sorted(projects, key=lambda n: (-n.mention_count, n.name.lower()))],
        "decisions": [{"decision": n.attrs.get("decision"), "reasoning": n.attrs.get("reasoning"),
                       "date": n.attrs.get("date") or (n.first_seen.strftime("%Y-%m-%d") if n.first_seen else None),
                       "chunk_id": n.attrs.get("chunk_id"), "raw_item_id": n.attrs.get("raw_item_id"),
                       "source": info.get(n.attrs.get("chunk_id"))} for n in decisions],
        "pending_actions": [{"description": n.attrs.get("description"), "owner": n.attrs.get("owner"),
                             "status": n.attrs.get("status"),
                             "last_seen": n.last_seen.strftime("%Y-%m-%d") if n.last_seen else None,
                             "chunk_id": n.attrs.get("chunk_id"), "raw_item_id": n.attrs.get("raw_item_id"),
                             "source": info.get(n.attrs.get("chunk_id"))} for n in actions],
    }
