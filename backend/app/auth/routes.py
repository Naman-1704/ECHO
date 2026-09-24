from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from jose import jwt
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.config import settings
from app.db.session import get_db
from app.db.models import User
from app.auth.google_oauth import get_auth_url, exchange_code_for_credentials, expiry_from_credentials

router = APIRouter(prefix="/auth", tags=["auth"])

JWT_ALGO = "HS256"


def create_session_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": datetime.utcnow() + timedelta(days=7)}
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGO)


@router.get("/login")
def login():
    """Redirects the successor's browser to Google's consent screen."""
    return RedirectResponse(get_auth_url())


@router.get("/callback")
def callback(code: str, db: Session = Depends(get_db)):
    """
    Google redirects here after consent. We exchange the code for tokens,
    fetch the user's email, upsert a User row, and hand back a session token.
    """
    creds = exchange_code_for_credentials(code)

    # Get the signed-in user's email via Google's userinfo endpoint
    import httpx
    resp = httpx.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {creds.token}"},
    )
    email = resp.json()["email"]

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(email=email)
        db.add(user)

    user.google_access_token = creds.token
    user.google_refresh_token = creds.refresh_token or user.google_refresh_token
    user.token_expiry = expiry_from_credentials(creds)
    db.commit()
    db.refresh(user)

    session_token = create_session_token(user.id)

    # Redirect back to the frontend with the session token (use an httpOnly cookie in production)
    redirect = RedirectResponse(f"{settings.frontend_url}/dashboard?token={session_token}")
    return redirect
