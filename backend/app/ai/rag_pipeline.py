from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import embed_text
from app.db.models import Chunk
from app.db.vector_store import similarity_search


def retrieve_context(db: Session, user_id: str, question: str, top_k: int = 8) -> list[Chunk]:
    """Semantic retrieval over this user's chunks (Chroma HNSW, metadata-filtered by user)."""
    if top_k <= 0:
        return []
    query_embedding = embed_text(question)
    return similarity_search(db, user_id=user_id, query_embedding=query_embedding, top_k=top_k)


def load_chunks(db: Session, user_id: str, chunk_ids: list[str]) -> list[Chunk]:
    """Loads specific chunks (e.g. a graph edge's evidence), keeping the given order and
    refusing anything that does not belong to this user."""
    ids = [c for c in dict.fromkeys(chunk_ids) if c]
    if not ids:
        return []
    rows = db.execute(select(Chunk).where(Chunk.id.in_(ids), Chunk.user_id == user_id)).scalars().all()
    by_id = {r.id: r for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def build_context_block(chunks: list[Chunk]) -> str:
    """Numbered context the model cites by index; each entry says what kind of item it is."""
    lines = []
    for i, chunk in enumerate(chunks, start=1):
        item = chunk.raw_item
        when = item.item_date.strftime("%Y-%m-%d") if item.item_date else "undated"
        label = f'{item.source} "{item.subject_or_title or "(untitled)"}", {when}'
        lines.append(f"[source: {i}] {label}\n{chunk.text}\n")
    return "\n".join(lines)
