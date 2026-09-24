from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings
from app.db.models import Base

# SQLite needs check_same_thread=False because FastAPI can hand requests to
# different threads, while a single SQLite connection is normally thread-bound.
# This is safe here because SessionLocal() opens a fresh connection per request.
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, echo=False, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Creates all tables (and the .db file itself, if it doesn't exist yet)."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session per request."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
