import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# NOTE: embedding dimension must match the embedding model you use.
# sentence-transformers/all-MiniLM-L6-v2 -> 384 dims. Not enforced by the column type
# here (SQLite has no native vector type — see db/vector_store.py), just a reference
# for anyone reading this later.
EMBEDDING_DIM = 384


class Base(DeclarativeBase):
    pass


def gen_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    """The successor who signs in and whose ingested-account data belongs to them."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    google_access_token: Mapped[str] = mapped_column(Text, nullable=True)
    google_refresh_token: Mapped[str] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    gmail_history_id: Mapped[str] = mapped_column(String, nullable=True)  # for incremental sync
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    raw_items: Mapped[list["RawItem"]] = relationship(back_populates="user")


class RawItem(Base):
    """One email or one Drive doc, before chunking."""
    __tablename__ = "raw_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String)          # "gmail" | "drive"
    source_id: Mapped[str] = mapped_column(String, index=True)  # gmail message id / drive file id
    subject_or_title: Mapped[str] = mapped_column(Text, nullable=True)
    participants: Mapped[dict] = mapped_column(JSON, nullable=True)  # {"from": ..., "to": [...]}
    raw_text: Mapped[str] = mapped_column(Text)
    item_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    is_redacted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="raw_items")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="raw_item")


class Chunk(Base):
    """
    A chunk of a raw item, plus its extracted structured facts. The embedding itself
    is NOT stored here — it lives in ChromaDB (see db/vector_store.py), keyed by this
    row's id. This table is the source of truth for chunk text/metadata; Chroma is
    the source of truth for the vector index.
    """
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    raw_item_id: Mapped[str] = mapped_column(ForeignKey("raw_items.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)  # denormalized for fast filtering
    text: Mapped[str] = mapped_column(Text)
    extracted: Mapped[dict] = mapped_column(JSON, nullable=True)  # entities/decisions/actions
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    raw_item: Mapped["RawItem"] = relationship(back_populates="chunks")


class AuditLog(Base):
    """Every query a user asks, for audit/trust purposes."""
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String)   # "chat_query" | "ingest_triggered" | ...
    detail: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    """
    One turn of a user's conversation with Echo. Both the user's question and the
    assistant's answer are stored as separate rows (role distinguishes them) so the
    full conversation can be replayed in order — this is what makes chat history
    persist across tabs/reloads instead of living only in frontend page state.
    """
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[dict] = mapped_column(JSON, nullable=True)  # only set on "assistant" rows
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
