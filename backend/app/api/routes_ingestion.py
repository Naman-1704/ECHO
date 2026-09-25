from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
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
    if not user.google_access_token or not user.google_refresh_token:
        raise HTTPException(
            status_code=400,
            detail="Google account access is not configured for this user. Complete the OAuth login flow first.",
        )

    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=500,
            detail="The backend Google OAuth client is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the environment.",
        )

    try:
        stats = run_gmail_ingestion(db, user, max_results=max_results)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Gmail sync failed: {exc}",
        ) from exc

    return stats
