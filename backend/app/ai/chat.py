from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.llm_client import chat_completion
from app.ai.query_router import plan_retrieval
from app.ai.rag_pipeline import build_context_block, load_chunks, retrieve_context
from app.db.models import User
from app.utils.links import source_url

_CHAT_PROMPT = (Path(__file__).parent / "prompts" / "chat_system_prompt.txt").read_text()

MAX_GRAPH_CHUNKS = 6     # evidence chunks pulled in because a graph fact points at them
MAX_CONTEXT_CHUNKS = 10  # hard cap on what goes into the prompt


def answer_question(db: Session, user: User, question: str) -> dict:
    """
    One chat turn:
      1. the router decides graph / hybrid / vector and fetches graph facts if relevant
      2. evidence chunks behind those facts + semantic hits are merged into ONE numbered list
      3. facts cite their evidence by the same [source: N] numbers the documents use
      4. the local model answers strictly from that context
    The response carries the route so the UI can show how the answer was produced.
    """
    plan = plan_retrieval(db, user, question)

    graph_ids = [c for f in plan.facts for c in f["chunk_ids"] if c]
    graph_chunks = load_chunks(db, user.id, graph_ids)[:MAX_GRAPH_CHUNKS]
    vector_chunks = retrieve_context(db, user.id, question, top_k=plan.vector_k)

    ordered, seen = [], set()
    for chunk in graph_chunks + vector_chunks:
        if chunk.id not in seen:
            seen.add(chunk.id)
            ordered.append(chunk)
    ordered = ordered[:MAX_CONTEXT_CHUNKS]

    if not ordered and not plan.facts:
        return {
            "answer": "I don't have any ingested data yet to answer this from. Try triggering a sync first.",
            "sources": [],
            "route": {"mode": "vector", "entities": [], "graph_facts": 0, "documents": 0},
        }

    index = {c.id: i + 1 for i, c in enumerate(ordered)}
    graph_lines = []
    for fact in plan.facts:
        marks = " ".join(f"[source: {index[c]}]" for c in fact["chunk_ids"] if c in index)
        graph_lines.append(f"- {fact['text']} {marks}".rstrip())
    graph_block = "\n".join(graph_lines) or "(no relationship facts matched this question)"

    prompt = _CHAT_PROMPT.format(
        graph_block=graph_block, context_block=build_context_block(ordered), question=question)
    answer_text = chat_completion(prompt, max_tokens=800, force_json=False)

    sources = []
    for i, chunk in enumerate(ordered, start=1):
        item = chunk.raw_item
        sources.append({
            "index": i, "chunk_id": chunk.id, "raw_item_id": item.id, "source_type": item.source,
            "subject": item.subject_or_title or "(untitled)",
            "date": item.item_date.strftime("%Y-%m-%d") if item.item_date else None,
            "url": source_url(item.source, item.source_id), "text_preview": chunk.text[:200],
        })

    return {
        "answer": answer_text,
        "sources": sources,
        "route": {"mode": plan.mode, "entities": plan.entities,
                  "graph_facts": len(plan.facts), "documents": len(ordered)},
    }
