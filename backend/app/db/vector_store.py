import chromadb
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Chunk

# One persistent client for the whole app — writes to a local folder (chroma_persist_dir),
# no server process required. This is created once at import time and reused everywhere.
# anonymized_telemetry=False: this project handles sensitive email data end-to-end locally
# on purpose — no reason for the vector store itself to phone home, even anonymously.
_client = chromadb.PersistentClient(
    path=settings.chroma_persist_dir,
    settings=chromadb.Settings(anonymized_telemetry=False),
)
_collection = _client.get_or_create_collection(
    name=settings.chroma_collection_name,
    metadata={"hnsw:space": "cosine"},  # cosine distance, matches normalized sentence-transformer embeddings
)


def add_chunk_embedding(chunk_id: str, user_id: str, raw_item_id: str, text: str, embedding: list[float]) -> None:
    """
    Called once per chunk during ingestion (see ingestion/jobs.py). The chunk's row
    and its extracted facts live in SQLite (db/models.py); only the vector + enough
    metadata to filter by user lives here in Chroma.
    """
    _collection.add(
        ids=[chunk_id],
        embeddings=[embedding],
        documents=[text],
        metadatas=[{"user_id": user_id, "raw_item_id": raw_item_id}],
    )


def similarity_search(db: Session, user_id: str, query_embedding: list[float], top_k: int = 8) -> list[Chunk]:
    """
    Queries Chroma's HNSW index for the top_k chunks closest to query_embedding,
    scoped to this user via metadata filtering (where={"user_id": ...}) — Chroma
    only searches within the matching subset, it doesn't scan everything and filter after.

    Chroma returns ids; we then fetch the matching rows from SQLite to get the actual
    text/extracted data, preserving the relevance order Chroma gave us.
    """
    result = _collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={"user_id": user_id},
    )
    ids_in_order = result["ids"][0] if result["ids"] else []
    if not ids_in_order:
        return []

    rows = db.execute(select(Chunk).where(Chunk.id.in_(ids_in_order))).scalars().all()
    rows_by_id = {row.id: row for row in rows}

    # Re-order to match Chroma's relevance ranking (dict lookup above loses order)
    return [rows_by_id[cid] for cid in ids_in_order if cid in rows_by_id]


def delete_chunk_embeddings(chunk_ids: list[str]) -> None:
    """Use this if you ever need to re-ingest/re-embed an item — delete stale vectors first."""
    if chunk_ids:
        _collection.delete(ids=chunk_ids)
