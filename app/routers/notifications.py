"""Notification center: bell badge + drawer + dedicated page."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from uuid import UUID as PyUUID

from app.database import get_db
from app.models.user import User
from app.models.notification import Notification
from app.services.auth import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _n_to_dict(n: Notification, actor: User | None = None) -> dict:
    return {
        "id": str(n.id),
        "type": n.type,
        "title": n.title or "",
        "body": n.body or "",
        "link": n.link or "",
        "actor": (
            {
                "id": str(actor.id),
                "username": actor.username,
                "display_name": actor.display_name,
                "avatar_url": actor.avatar_url or "",
            } if actor else None
        ),
        "is_read": bool(n.is_read),
        "created_at": n.created_at.isoformat() if n.created_at else "",
    }


@router.get("")
async def list_notifications(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Most-recent notifications first (capped at 50)."""
    limit = max(1, min(limit, 100))
    q = await db.execute(
        select(Notification, User)
        .outerjoin(User, User.id == Notification.actor_id)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    rows = q.all()
    return {"notifications": [_n_to_dict(n, a) for n, a in rows]}


@router.get("/unread-count")
async def unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Used by the bell badge — must stay tiny since clients hit it ~1Hz."""
    q = await db.execute(
        select(Notification.id).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
    )
    return {"count": len(q.scalars().all())}


@router.post("/mark-all-read")
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)
        .values(is_read=True)
    )
    return {"ok": True}


@router.post("/{nid}/read")
async def mark_one_read(
    nid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        u = PyUUID(nid)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid id")
    n = (await db.execute(
        select(Notification).where(
            Notification.id == u, Notification.user_id == current_user.id
        )
    )).scalar_one_or_none()
    if not n:
        raise HTTPException(status_code=404, detail="找不到通知")
    n.is_read = True
    db.add(n)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Internal helper — call from other routers when an event fires.
# ---------------------------------------------------------------------------
async def create_notification(
    db: AsyncSession,
    *,
    user_id,
    n_type: str,
    title: str = "",
    body: str = "",
    link: str = "",
    actor_id=None,
):
    """Insert a notification row. Caller is responsible for committing."""
    n = Notification(
        user_id=user_id,
        type=n_type,
        title=title,
        body=body,
        link=link,
        actor_id=actor_id,
    )
    db.add(n)
    return n
