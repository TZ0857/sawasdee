"""User-facing reporting endpoint.

Any logged-in user can report a user / post / message. Reports land in the
moderation queue surfaced by the /admin dashboard. Required for App Store
objectionable-content compliance.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.report import Report
from app.services.auth import get_current_user

router = APIRouter(prefix="/api/reports", tags=["reports"])

_VALID_TARGETS = {"user", "post", "message"}


class ReportCreate(BaseModel):
    target_type: str
    target_id: str
    reason: str = ""
    detail: Optional[str] = ""


@router.post("")
async def create_report(
    req: ReportCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.target_type not in _VALID_TARGETS:
        raise HTTPException(status_code=400, detail="無效的檢舉對象類型")
    try:
        target_uuid = uuid.UUID(req.target_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="無效的對象 ID")

    report = Report(
        reporter_id=user.id,
        target_type=req.target_type,
        target_id=target_uuid,
        reason=(req.reason or "")[:50],
        detail=(req.detail or "")[:2000],
    )
    db.add(report)
    await db.flush()
    return {"ok": True, "id": str(report.id), "message": "已收到你的檢舉，我們會盡快處理"}
