from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.llm_client import chat_completion
from app.ai.rag_pipeline import retrieve_context, build_context_block

_CHAT_PROMPT = (Path(__file__).parent / "prompts" / "chat_system_prompt.txt").read_text()


def answer_question(db: Session, user_id: str, question: str) -> dict:
    """
    Full RAG chat turn: retrieve relevant chunks, build a grounded prompt, call the
    local model, return both the answer and the source chunks so the frontend can
    render citations.
    """
    chunks = retrieve_context(db, user_id=user_id, question=question, top_k=8)

    if not chunks:
        return {
            "answer": "I don't have any ingested data yet to answer this from. Try triggering a sync first.",
            "sources": [],
        }

    context_block = build_context_block(chunks)
    prompt = _CHAT_PROMPT.format(context_block=context_block, question=question)

    answer_text = chat_completion(prompt, max_tokens=800, force_json=False)

    return {
        "answer": answer_text,
        "sources": [
            {"index": i + 1, "raw_item_id": c.raw_item_id, "text_preview": c.text[:200]}
            for i, c in enumerate(chunks)
        ],
    }
