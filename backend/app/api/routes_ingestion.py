from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User
from app.dependencies import get_current_user
from app.ingestion.jobs import run_gmail_ingestion

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/sync")
def trigger_sync(
    max_results: int = 10,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    MVP: runs synchronously and returns stats directly (fine for max_results=50 during dev).
    For real mailbox volumes, move this to a BackgroundTask or Celery job and add a
    GET /ingestion/status endpoint the frontend can poll instead.
    """
    stats = run_gmail_ingestion(db, user, max_results=max_results)
    return stats
