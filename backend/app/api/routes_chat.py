from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, AuditLog, ChatMessage
from app.dependencies import get_current_user
from app.ai.chat import answer_question

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str


@router.post("/ask")
def ask(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = answer_question(db, user_id=user.id, question=body.question)

    # Persist both turns so the conversation survives a reload/tab switch — see /history below.
    db.add(ChatMessage(user_id=user.id, role="user", content=body.question))
    db.add(ChatMessage(user_id=user.id, role="assistant", content=result["answer"], sources=result["sources"]))
    db.add(AuditLog(user_id=user.id, action="chat_query", detail=body.question))
    db.commit()

    return result


@router.get("/history")
def get_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns this user's full conversation, oldest first, in the same shape the
    frontend already renders live turns in — so loading history and loading a
    fresh answer both flow through one rendering path on the frontend.
    """
    messages = db.execute(
        select(ChatMessage).where(ChatMessage.user_id == user.id).order_by(ChatMessage.created_at)
    ).scalars().all()

    return {
        "turns": [
            {"role": m.role, "content": m.content, "sources": m.sources or []}
            for m in messages
        ]
    }


@router.delete("/history")
def clear_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lets the user start a fresh conversation without it being mixed into the record."""
    db.execute(
        ChatMessage.__table__.delete().where(ChatMessage.user_id == user.id)
    )
    db.commit()
    return {"cleared": True}
