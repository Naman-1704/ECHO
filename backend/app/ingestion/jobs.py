from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import embed_batch
from app.ai.extraction import extract_structured_facts
from app.db.models import Chunk, RawItem, User, gen_uuid
from app.db.vector_store import add_chunk_embedding
from app.graph.builder import rebuild_graph
from app.ingestion.chunking import chunk_text
from app.ingestion.drive_connector import fetch_files
from app.ingestion.gmail_connector import fetch_messages
from app.ingestion.redaction import redact_patterns, should_exclude

VALID_SOURCES = ("gmail", "drive", "all")


def _ingest_items(db: Session, user: User, items: list[dict], source: str, stats: dict) -> None:
    """
    The shared pipeline for every source: skip already-seen items, apply the privacy
    filter BEFORE anything is stored/embedded/extracted, then chunk -> embed -> extract.

    Each item is committed on its own. The embedding goes to Chroma as soon as it is
    created, so committing per item (instead of once at the end) keeps the two stores
    from drifting apart for long if a run is interrupted part-way through.
    """
    for it in items:
        already = db.execute(select(RawItem.id).where(
            RawItem.user_id == user.id, RawItem.source == source, RawItem.source_id == it["source_id"],
        )).first()
        if already:
            stats["skipped_existing"] += 1
            continue

        if should_exclude(it["subject_or_title"], it["raw_text"]):
            stats["excluded"] += 1
            continue  # never store, embed, or extract from excluded items

        clean_text = redact_patterns(it["raw_text"])
        raw_item = RawItem(
            user_id=user.id, source=source, source_id=it["source_id"],
            subject_or_title=it["subject_or_title"], participants=it["participants"],
            raw_text=clean_text, item_date=it["item_date"],
        )
        db.add(raw_item)
        db.flush()

        pieces = chunk_text(clean_text)
        if pieces:
            embeddings = embed_batch(pieces)
            for piece, vector in zip(pieces, embeddings):
                extracted = extract_structured_facts(piece)
                chunk_id = gen_uuid()
                db.add(Chunk(id=chunk_id, raw_item_id=raw_item.id, user_id=user.id,
                             text=piece, extracted=extracted))
                add_chunk_embedding(chunk_id=chunk_id, user_id=user.id, raw_item_id=raw_item.id,
                                    text=piece, embedding=vector)
                stats["chunks_created"] += 1
        db.commit()
        stats["by_source"][source] += 1


def run_ingestion(db: Session, user: User, source: str = "gmail", max_results: int = 50) -> dict:
    """
    Pulls from Gmail, Drive, or both, ingests everything new, then rebuilds the knowledge
    graph (a fast, model-free step) so the Network / Attention / Report views are current.
    Source failures are collected in stats["errors"] rather than raised, so one broken
    source does not discard the other's work.

    Synchronous MVP version: fine for a few dozen items per click. For full-mailbox volume
    move this to a background worker and add a status endpoint to poll.
    """
    if source not in VALID_SOURCES:
        raise ValueError(f"source must be one of {VALID_SOURCES}")

    stats = {"pulled": 0, "excluded": 0, "skipped_existing": 0, "chunks_created": 0,
             "by_source": {"gmail": 0, "drive": 0}, "errors": [], "next_page_token": None}

    plan = []
    if source in ("gmail", "all"):
        plan.append(("gmail", lambda: fetch_messages(user.google_access_token, user.google_refresh_token,
                                                     max_results=max_results)))
    if source in ("drive", "all"):
        plan.append(("drive", lambda: fetch_files(user.google_access_token, user.google_refresh_token,
                                                  max_results=max(5, max_results // 2))))

    for name, fetch in plan:
        try:
            items, next_token = fetch()
        except Exception as exc:
            db.rollback()
            stats["errors"].append(f"{name}: {exc}")
            continue
        stats["pulled"] += len(items)
        if name == "gmail":
            stats["next_page_token"] = next_token
        try:
            _ingest_items(db, user, items, name, stats)
        except Exception as exc:
            db.rollback()
            stats["errors"].append(f"{name}: ingestion stopped part-way: {exc}")

    if stats["chunks_created"] > 0:
        stats["graph"] = rebuild_graph(db, user)
    return stats


def run_gmail_ingestion(db: Session, user: User, max_results: int = 50) -> dict:
    """Kept for backward compatibility with older callers."""
    return run_ingestion(db, user, source="gmail", max_results=max_results)
