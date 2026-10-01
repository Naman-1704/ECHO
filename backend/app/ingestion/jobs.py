from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.models import User, RawItem, Chunk, gen_uuid
from app.db.vector_store import add_chunk_embedding
from app.ingestion.gmail_connector import fetch_messages
from app.ingestion.chunking import chunk_text
from app.ingestion.redaction import should_exclude, redact_patterns
from app.ai.embeddings import embed_batch
from app.ai.extraction import extract_structured_facts


def run_gmail_ingestion(db: Session, user: User, max_results: int = 10) -> dict:
    """
    Synchronous MVP version — runs inline via FastAPI BackgroundTasks.
    For production volume (thousands of emails), swap this for a Celery task
    so it survives request timeouts and can retry on failure.

    Note on consistency: chunk metadata goes to SQLite (committed at the end, in one
    transaction) while embeddings go to Chroma immediately as each chunk is created.
    If something crashes mid-run before db.commit(), Chroma may end up with vectors
    for chunks that never made it into SQLite. Fine for an MVP; if this becomes a
    real problem, either commit SQLite per-chunk instead of in one batch, or add a
    cleanup pass that deletes Chroma ids with no matching SQLite row.
    """
    messages, next_page_token = fetch_messages(
        user.google_access_token, user.google_refresh_token, max_results=max_results
    )

    stats = {"pulled": len(messages), "excluded": 0, "chunks_created": 0}

    for msg in messages:
        # Skip if we already have this message
        existing = db.execute(
            select(RawItem).where(RawItem.source_id == msg["source_id"], RawItem.user_id == user.id)
        ).scalar_one_or_none()
        if existing:
            continue

        if should_exclude(msg["subject_or_title"], msg["raw_text"]):
            stats["excluded"] += 1
            continue  # never store, embed, or extract from excluded items

        clean_text = redact_patterns(msg["raw_text"])

        raw_item = RawItem(
            user_id=user.id,
            source="gmail",
            source_id=msg["source_id"],
            subject_or_title=msg["subject_or_title"],
            participants=msg["participants"],
            raw_text=clean_text,
            item_date=msg["item_date"],
        )
        db.add(raw_item)
        db.flush()  # get raw_item.id without committing yet

        pieces = chunk_text(clean_text)
        if not pieces:
            continue

        embeddings = embed_batch(pieces)

        for piece, vector in zip(pieces, embeddings):
            extracted = extract_structured_facts(piece)
            chunk_id = gen_uuid()  # generate explicitly so we can use it for Chroma right away

            chunk = Chunk(
                id=chunk_id,
                raw_item_id=raw_item.id,
                user_id=user.id,
                text=piece,
                extracted=extracted,
            )
            db.add(chunk)

            # Vector goes to Chroma, not SQLite — see db/vector_store.py
            add_chunk_embedding(
                chunk_id=chunk_id,
                user_id=user.id,
                raw_item_id=raw_item.id,
                text=piece,
                embedding=vector,
            )

            stats["chunks_created"] += 1

    db.commit()
    stats["next_page_token"] = next_page_token
    return stats
