"""Admin / moderation dashboard API.

Every endpoint is guarded by `require_admin`, which rejects any token whose
user does not have `is_admin = TRUE`. The /admin HTML page itself contains no
data — it only renders these endpoints' responses — so the panel is safe even
though its URL is public.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.post import Post
from app.models.report import Report, ReportStatus
from app.services.auth import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="需要管理員權限")
    return user


# ─────────────────────────── Dashboard stats ───────────────────────────
@router.get("/stats")
async def stats(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    async def count(stmt):
        return (await db.execute(stmt)).scalar_one()

    total_users = await count(select(func.count(User.id)))
    subscribed = await count(select(func.count(User.id)).where(User.is_subscribed.is_(True)))
    online = await count(select(func.count(User.id)).where(User.is_online.is_(True)))
    banned = await count(select(func.count(User.id)).where(User.is_active.is_(False)))
    total_posts = await count(select(func.count(Post.id)))
    pending_reports = await count(
        select(func.count(Report.id)).where(Report.status == ReportStatus.pending)
    )
    return {
        "total_users": total_users,
        "subscribed": subscribed,
        "online": online,
        "banned": banned,
        "total_posts": total_posts,
        "pending_reports": pending_reports,
    }


# ─────────────────────────────── Users ─────────────────────────────────
def _user_row(u: User) -> dict:
    return {
        "id": str(u.id),
        "username": u.username,
        "display_name": u.display_name,
        "email": u.email,
        "gender": u.gender.value if u.gender else "",
        "nationality": u.nationality.value if u.nationality else "",
        "avatar_url": u.avatar_url or "",
        "is_active": u.is_active,
        "is_verified": u.is_verified,
        "is_subscribed": u.is_subscribed,
        "is_admin": getattr(u, "is_admin", False),
        "is_online": u.is_online,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@router.get("/users")
async def list_users(
    q: Optional[str] = None,
    limit: int = 100,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            User.username.ilike(like),
            User.display_name.ilike(like),
            User.email.ilike(like),
        ))
    stmt = stmt.order_by(User.created_at.desc()).limit(min(limit, 300))
    rows = (await db.execute(stmt)).scalars().all()
    return [_user_row(u) for u in rows]


async def _get_user_or_404(db: AsyncSession, user_id: str) -> User:
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if u is None:
        raise HTTPException(status_code=404, detail="找不到使用者")
    return u


@router.post("/users/{user_id}/toggle-ban")
async def toggle_ban(user_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    u = await _get_user_or_404(db, user_id)
    if u.id == admin.id:
        raise HTTPException(status_code=400, detail="不能停權自己")
    if getattr(u, "is_admin", False):
        raise HTTPException(status_code=400, detail="不能停權其他管理員")
    u.is_active = not u.is_active
    return {"id": str(u.id), "is_active": u.is_active}


@router.post("/users/{user_id}/toggle-verify")
async def toggle_verify(user_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    u = await _get_user_or_404(db, user_id)
    u.is_verified = not u.is_verified
    return {"id": str(u.id), "is_verified": u.is_verified}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    u = await _get_user_or_404(db, user_id)
    if u.id == admin.id:
        raise HTTPException(status_code=400, detail="不能刪除自己")
    if getattr(u, "is_admin", False):
        raise HTTPException(status_code=400, detail="不能刪除其他管理員")
    await db.delete(u)
    return {"ok": True}


# ─────────────────────────────── Posts ─────────────────────────────────
@router.get("/posts")
async def list_posts(
    limit: int = 60,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Post, User)
        .join(User, Post.author_id == User.id)
        .order_by(Post.created_at.desc())
        .limit(min(limit, 200))
    )
    rows = (await db.execute(stmt)).all()
    out = []
    for post, author in rows:
        out.append({
            "id": str(post.id),
            "content": post.content or "",
            "image_url": post.image_url or "",
            "video_url": post.video_url or "",
            "likes_count": post.likes_count,
            "comments_count": post.comments_count,
            "created_at": post.created_at.isoformat() if post.created_at else None,
            "author": {
                "username": author.username,
                "display_name": author.display_name,
                "avatar_url": author.avatar_url or "",
            },
        })
    return out


@router.delete("/posts/{post_id}")
async def delete_post(post_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(Post).where(Post.id == post_id))).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="找不到動態")
    await db.delete(p)
    return {"ok": True}


# ────────────────────────────── Reports ────────────────────────────────
@router.get("/reports")
async def list_reports(
    status: str = "pending",
    limit: int = 100,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Report)
    if status in ("pending", "resolved", "dismissed"):
        stmt = stmt.where(Report.status == ReportStatus(status))
    stmt = stmt.order_by(Report.created_at.desc()).limit(min(limit, 300))
    reports = (await db.execute(stmt)).scalars().all()

    # Resolve reporter usernames in one extra pass
    reporter_ids = [r.reporter_id for r in reports if r.reporter_id]
    names = {}
    if reporter_ids:
        urows = (await db.execute(select(User).where(User.id.in_(reporter_ids)))).scalars().all()
        names = {u.id: u.username for u in urows}

    return [{
        "id": str(r.id),
        "reporter": names.get(r.reporter_id, "（已刪除）"),
        "target_type": r.target_type,
        "target_id": str(r.target_id),
        "reason": r.reason,
        "detail": r.detail or "",
        "status": r.status.value,
        "resolution": r.resolution or "",
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in reports]


class ResolveReq(BaseModel):
    action: str  # 'dismiss' | 'resolve' | 'delete_target' | 'ban_target'


@router.post("/reports/{report_id}/resolve")
async def resolve_report(
    report_id: str,
    req: ResolveReq,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    r = (await db.execute(select(Report).where(Report.id == report_id))).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="找不到檢舉")

    action = req.action
    note = ""

    if action == "delete_target" and r.target_type == "post":
        p = (await db.execute(select(Post).where(Post.id == r.target_id))).scalar_one_or_none()
        if p is not None:
            await db.delete(p)
        note = "已刪除被檢舉的動態"
        r.status = ReportStatus.resolved
    elif action == "ban_target" and r.target_type == "user":
        u = (await db.execute(select(User).where(User.id == r.target_id))).scalar_one_or_none()
        if u is not None and not getattr(u, "is_admin", False):
            u.is_active = False
            note = "已停權被檢舉的使用者"
        r.status = ReportStatus.resolved
    elif action == "dismiss":
        note = "已忽略（無問題）"
        r.status = ReportStatus.dismissed
    else:  # 'resolve' / fallback
        note = "已標記處理完成"
        r.status = ReportStatus.resolved

    r.resolution = note
    r.resolved_at = datetime.utcnow()
    return {"id": str(r.id), "status": r.status.value, "resolution": note}
