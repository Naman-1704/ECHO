from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db.models import AuditLog, User
from app.db.session import get_db
from app.dependencies import get_current_user
from app.reports.handover import build_report_data, render_markdown, render_pdf

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/handover")
def handover_report(
    format: str = Query("pdf", pattern="^(pdf|md)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = build_report_data(db, user)
    db.add(AuditLog(user_id=user.id, action="report_exported", detail=format))
    db.commit()
    if format == "md":
        body, media, ext = render_markdown(data).encode("utf-8"), "text/markdown; charset=utf-8", "md"
    else:
        body, media, ext = render_pdf(data), "application/pdf", "pdf"
    return Response(content=body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="echo-handover-report.{ext}"',
                             "Access-Control-Expose-Headers": "Content-Disposition"})
