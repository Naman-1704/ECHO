from sqlalchemy.orm import Session

from app.ai.embeddings import embed_text
from app.db.vector_store import similarity_search
from app.db.models import Chunk


def retrieve_context(db: Session, user_id: str, question: str, top_k: int = 8) -> list[Chunk]:
    """
    Vector-only retrieval for the MVP. Once the graph layer (Week 4-5 in the timeline)
    is built, this is where you'd add a query_router.py that decides between graph
    lookup (for "who worked on X" type questions) and this vector search (for "why"
    / open-ended questions), then merges both into one context set.
    """
    query_embedding = embed_text(question)
    return similarity_search(db, user_id=user_id, query_embedding=query_embedding, top_k=top_k)


def build_context_block(chunks: list[Chunk]) -> str:
    """Formats retrieved chunks into a numbered context block the LLM can cite by index."""
    lines = []
    for i, chunk in enumerate(chunks, start=1):
        lines.append(f"[source: {i}] (from item {chunk.raw_item_id})\n{chunk.text}\n")
    return "\n".join(lines)
