from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, AuditLog
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

    db.add(AuditLog(user_id=user.id, action="chat_query", detail=body.question))
    db.commit()

    return result
