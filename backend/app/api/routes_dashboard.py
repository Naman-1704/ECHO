from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, RawItem, Chunk
from app.dependencies import get_current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def get_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Aggregates the `extracted` JSON stored on every chunk (see ai/extraction.py) into
    de-duplicated people/projects/decisions/action_items lists, each carrying enough
    detail to link back to its source chunk — this is what lets the frontend show
    "seen in N emails" and jump to source text for any fact on screen.
    """
    chunks = list(db.execute(select(Chunk).where(Chunk.user_id == user.id)).scalars().all())
    total_emails = db.execute(
        select(RawItem).where(RawItem.user_id == user.id)
    ).scalars().all()

    people: dict[str, dict] = {}
    projects: dict[str, dict] = {}
    decisions: list[dict] = []
    action_items: list[dict] = []

    for chunk in chunks:
        extracted = chunk.extracted or {}

        for p in extracted.get("people", []):
            name = (p.get("name") or "").strip()
            if not name:
                continue
            entry = people.setdefault(name, {"name": name, "context_samples": [], "mention_count": 0})
            entry["mention_count"] += 1
            if p.get("role_or_context") and len(entry["context_samples"]) < 3:
                entry["context_samples"].append(p["role_or_context"])

        for proj in extracted.get("projects", []):
            name = (proj.get("name") or "").strip()
            if not name:
                continue
            entry = projects.setdefault(name, {"name": name, "context_samples": [], "mention_count": 0})
            entry["mention_count"] += 1
            if proj.get("context") and len(entry["context_samples"]) < 3:
                entry["context_samples"].append(proj["context"])

        for d in extracted.get("decisions", []):
            if d.get("decision"):
                decisions.append({**d, "chunk_id": chunk.id, "raw_item_id": chunk.raw_item_id})

        for a in extracted.get("action_items", []):
            if a.get("description"):
                action_items.append({**a, "chunk_id": chunk.id, "raw_item_id": chunk.raw_item_id})

    return {
        "stats": {
            "total_emails_ingested": len(total_emails),
            "total_chunks_processed": len(chunks),
            "unique_people": len(people),
            "unique_projects": len(projects),
        },
        "people": sorted(people.values(), key=lambda x: -x["mention_count"]),
        "projects": sorted(projects.values(), key=lambda x: -x["mention_count"]),
        "decisions": decisions,
        "pending_actions": [a for a in action_items if a.get("status") != "resolved"],
    }
