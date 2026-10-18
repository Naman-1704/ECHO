from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models import AuditLog, User
from app.db.session import get_db
from app.dependencies import get_current_user
from app.ingestion.jobs import run_ingestion

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/sync")
def trigger_sync(
    source: str = Query("gmail", pattern="^(gmail|drive|all)$"),
    max_results: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Ingest new Gmail messages and/or Drive documents, then refresh the knowledge graph.
    Runs synchronously (fine at ~50 items). If every requested source failed and nothing
    was ingested, responds 502 with the reasons instead of a misleading success.
    """
    stats = run_ingestion(db, user, source=source, max_results=max_results)
    db.add(AuditLog(user_id=user.id, action="ingest_triggered",
                    detail=f"source={source} pulled={stats['pulled']} chunks={stats['chunks_created']}"))
    db.commit()
    if stats["errors"] and stats["pulled"] == 0:
        raise HTTPException(status_code=502, detail="; ".join(stats["errors"]))
    return stats
