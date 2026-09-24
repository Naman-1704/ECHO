from fastapi import Depends, Header, HTTPException
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.db.models import User
from app.auth.routes import JWT_ALGO


def get_current_user(authorization: str = Header(...), db: Session = Depends(get_db)) -> User:
    """Expects header: Authorization: Bearer <session_token>"""
    token = authorization.replace("Bearer ", "")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGO])
        user_id = payload["sub"]
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user
