"""Admin / moderation dashboard API.

Every data endpoint is guarded by `require_admin`, which rejects any token
whose user does not have `is_admin = TRUE`. The /admin HTML page contains no
data — it only renders these endpoints' responses — so the panel is safe even
though its URL is public.

Sections: dashboard stats, users, posts, stories, photos/albums, gatherings,
subscriptions (Premium) and reports.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.post import Post, Comment, Story
from app.models.album import Album, Photo, AlbumAccessRequest, AlbumType, AccessStatus
from app.models.gathering import Gathering
from app.models.report import Report, ReportStatus
from app.services.auth import get_current_user, verify_password, create_access_token

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="需要管理員權限")
    return user


# ─────────────────── Dedicated back-office login ───────────────────────
class AdminLoginReq(BaseModel):
    username: str
    password: str


@router.post("/login")
async def admin_login(req: AdminLoginReq, db: AsyncSession = Depends(get_db)):
    ident = (req.username or "").strip().lower()
    user = (await db.execute(select(User).where(or_(
        func.lower(User.username) == ident,
        func.lower(User.email) == ident,
    )))).scalar_one_or_none()
    if user is None or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="此帳號沒有後台權限")
    token = create_access_token(data={"sub": str(user.id)})
    return {
        "access_token": token,
        "token_type": "bearer",
        "admin": {"username": user.username, "display_name": user.display_name},
    }


# ─────────────────────────── Dashboard stats ───────────────────────────
@router.get("/stats")
async def stats(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    now = datetime.utcnow()

    async def count(stmt):
        return (await db.execute(stmt)).scalar_one()

    return {
        "total_users": await count(select(func.count(User.id))),
        "subscribed": await count(select(func.count(User.id)).where(User.is_subscribed.is_(True))),
        "online": await count(select(func.count(User.id)).where(User.is_online.is_(True))),
        "banned": await count(select(func.count(User.id)).where(User.is_active.is_(False))),
        "total_posts": await count(select(func.count(Post.id))),
        "active_stories": await count(
            select(func.count(Story.id)).where(and_(Story.is_active.is_(True), Story.expires_at > now))
        ),
        "total_photos": await count(select(func.count(Photo.id))),
        "active_gatherings": await count(
            select(func.count(Gathering.id)).where(and_(Gathering.is_active.is_(True), Gathering.expires_at > now))
        ),
        "pending_album_requests": await count(
            select(func.count(AlbumAccessRequest.id)).where(AlbumAccessRequest.status == AccessStatus.pending)
        ),
        "pending_reports": await count(
            select(func.count(Report.id)).where(Report.status == ReportStatus.pending)
        ),
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
        "age": u.age,
        "location": u.location or "",
        "avatar_url": u.avatar_url or "",
        "is_active": u.is_active,
        "is_verified": u.is_verified,
        "is_subscribed": u.is_subscribed,
        "is_admin": getattr(u, "is_admin", False),
        "is_online": u.is_online,
        "subscription_expires_at": u.subscription_expires_at.isoformat() if u.subscription_expires_at else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@router.get("/users")
async def list_users(
    q: Optional[str] = None,
    filter: str = "all",
    limit: int = 200,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            User.username.ilike(like), User.display_name.ilike(like), User.email.ilike(like),
        ))
    if filter == "subscribed":
        stmt = stmt.where(User.is_subscribed.is_(True))
    elif filter == "online":
        stmt = stmt.where(User.is_online.is_(True))
    elif filter == "banned":
        stmt = stmt.where(User.is_active.is_(False))
    elif filter == "verified":
        stmt = stmt.where(User.is_verified.is_(True))
    stmt = stmt.order_by(User.created_at.desc()).limit(min(limit, 400))
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


class GrantReq(BaseModel):
    days: int = 30


@router.post("/users/{user_id}/grant-premium")
async def grant_premium(user_id: str, req: GrantReq, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    u = await _get_user_or_404(db, user_id)
    now = datetime.utcnow()
    base = u.subscription_expires_at if (u.subscription_expires_at and u.subscription_expires_at > now) else now
    u.is_subscribed = True
    u.subscription_expires_at = base + timedelta(days=max(1, req.days))
    return {"id": str(u.id), "is_subscribed": True, "subscription_expires_at": u.subscription_expires_at.isoformat()}


@router.post("/users/{user_id}/revoke-premium")
async def revoke_premium(user_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    u = await _get_user_or_404(db, user_id)
    u.is_subscribed = False
    u.subscription_expires_at = None
    return {"id": str(u.id), "is_subscribed": False}


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
    q: Optional[str] = None,
    limit: int = 80,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Post, User).join(User, Post.author_id == User.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Post.content.ilike(like), User.username.ilike(like), User.display_name.ilike(like)))
    stmt = stmt.order_by(Post.created_at.desc()).limit(min(limit, 200))
    rows = (await db.execute(stmt)).all()
    return [{
        "id": str(post.id),
        "content": post.content or "",
        "image_url": post.image_url or "",
        "video_url": post.video_url or "",
        "likes_count": post.likes_count,
        "comments_count": post.comments_count,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "author": {"username": author.username, "display_name": author.display_name, "avatar_url": author.avatar_url or ""},
    } for post, author in rows]


@router.delete("/posts/{post_id}")
async def delete_post(post_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(Post).where(Post.id == post_id))).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="找不到動態")
    await db.delete(p)
    return {"ok": True}


# ────────────────────────────── Stories ────────────────────────────────
@router.get("/stories")
async def list_stories(
    filter: str = "active",
    limit: int = 80,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()
    stmt = select(Story, User).join(User, Story.author_id == User.id)
    if filter == "active":
        stmt = stmt.where(and_(Story.is_active.is_(True), Story.expires_at > now))
    elif filter == "expired":
        stmt = stmt.where(or_(Story.is_active.is_(False), Story.expires_at <= now))
    stmt = stmt.order_by(Story.created_at.desc()).limit(min(limit, 200))
    rows = (await db.execute(stmt)).all()
    return [{
        "id": str(s.id),
        "image_url": s.image_url or "",
        "caption": s.caption or "",
        "is_active": s.is_active and s.expires_at > now,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "expires_at": s.expires_at.isoformat() if s.expires_at else None,
        "author": {"username": a.username, "display_name": a.display_name, "avatar_url": a.avatar_url or ""},
    } for s, a in rows]


@router.delete("/stories/{story_id}")
async def delete_story(story_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(Story).where(Story.id == story_id))).scalar_one_or_none()
    if s is None:
        raise HTTPException(status_code=404, detail="找不到限時動態")
    await db.delete(s)
    return {"ok": True}


# ───────────────────────── Photos / Albums ─────────────────────────────
@router.get("/photos")
async def list_photos(
    filter: str = "all",
    limit: int = 90,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Photo, Album, User)
        .join(Album, Photo.album_id == Album.id)
        .join(User, Album.owner_id == User.id)
    )
    if filter == "private":
        stmt = stmt.where(Album.album_type == AlbumType.private)
    elif filter == "public":
        stmt = stmt.where(Album.album_type == AlbumType.public)
    stmt = stmt.order_by(Photo.created_at.desc()).limit(min(limit, 240))
    rows = (await db.execute(stmt)).all()
    return [{
        "id": str(ph.id),
        "image_url": ph.image_url or "",
        "caption": ph.caption or "",
        "album_type": album.album_type.value if album.album_type else "public",
        "album_title": album.title or "",
        "owner": {"username": owner.username, "display_name": owner.display_name, "avatar_url": owner.avatar_url or ""},
        "created_at": ph.created_at.isoformat() if ph.created_at else None,
    } for ph, album, owner in rows]


@router.delete("/photos/{photo_id}")
async def delete_photo(photo_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    ph = (await db.execute(select(Photo).where(Photo.id == photo_id))).scalar_one_or_none()
    if ph is None:
        raise HTTPException(status_code=404, detail="找不到照片")
    await db.delete(ph)
    return {"ok": True}


@router.get("/album-requests")
async def list_album_requests(
    status: str = "pending",
    limit: int = 100,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(AlbumAccessRequest, Album, User)
        .join(Album, AlbumAccessRequest.album_id == Album.id)
        .join(User, AlbumAccessRequest.requester_id == User.id)
    )
    if status in ("pending", "approved", "rejected"):
        stmt = stmt.where(AlbumAccessRequest.status == AccessStatus(status))
    stmt = stmt.order_by(AlbumAccessRequest.created_at.desc()).limit(min(limit, 200))
    rows = (await db.execute(stmt)).all()
    return [{
        "id": str(r.id),
        "status": r.status.value,
        "album_title": album.title or "",
        "requester": {"username": req.username, "display_name": req.display_name, "avatar_url": req.avatar_url or ""},
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r, album, req in rows]


class AlbumReqAction(BaseModel):
    action: str  # approve | reject


@router.post("/album-requests/{request_id}/resolve")
async def resolve_album_request(request_id: str, body: AlbumReqAction, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    r = (await db.execute(select(AlbumAccessRequest).where(AlbumAccessRequest.id == request_id))).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="找不到申請")
    r.status = AccessStatus.approved if body.action == "approve" else AccessStatus.rejected
    return {"id": str(r.id), "status": r.status.value}


# ──────────────────────────── Gatherings ───────────────────────────────
@router.get("/gatherings")
async def list_gatherings(
    q: Optional[str] = None,
    filter: str = "active",
    limit: int = 80,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()
    stmt = select(Gathering, User).join(User, Gathering.host_id == User.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Gathering.title.ilike(like), Gathering.location.ilike(like)))
    if filter == "active":
        stmt = stmt.where(and_(Gathering.is_active.is_(True), Gathering.expires_at > now))
    elif filter == "expired":
        stmt = stmt.where(or_(Gathering.is_active.is_(False), Gathering.expires_at <= now))
    stmt = stmt.order_by(Gathering.created_at.desc()).limit(min(limit, 200))
    rows = (await db.execute(stmt)).all()
    return [{
        "id": str(g.id),
        "title": g.title,
        "type": g.type,
        "location": g.location,
        "max_slots": g.max_slots,
        "current_slots": g.current_slots,
        "is_active": g.is_active and g.expires_at > now,
        "expires_at": g.expires_at.isoformat() if g.expires_at else None,
        "host": {"username": host.username, "display_name": host.display_name, "avatar_url": host.avatar_url or ""},
    } for g, host in rows]


@router.post("/gatherings/{gathering_id}/toggle-active")
async def toggle_gathering(gathering_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    g = (await db.execute(select(Gathering).where(Gathering.id == gathering_id))).scalar_one_or_none()
    if g is None:
        raise HTTPException(status_code=404, detail="找不到組局")
    g.is_active = not g.is_active
    return {"id": str(g.id), "is_active": g.is_active}


@router.delete("/gatherings/{gathering_id}")
async def delete_gathering(gathering_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    g = (await db.execute(select(Gathering).where(Gathering.id == gathering_id))).scalar_one_or_none()
    if g is None:
        raise HTTPException(status_code=404, detail="找不到組局")
    await db.delete(g)
    return {"ok": True}


# ─────────────────────────── Subscriptions ─────────────────────────────
@router.get("/subscriptions")
async def list_subscriptions(
    q: Optional[str] = None,
    filter: str = "active",
    limit: int = 200,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()
    stmt = select(User)
    if filter == "active":
        stmt = stmt.where(User.is_subscribed.is_(True))
    elif filter == "expired":
        stmt = stmt.where(and_(
            User.subscription_expires_at.is_not(None),
            User.subscription_expires_at < now,
        ))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(User.username.ilike(like), User.display_name.ilike(like), User.email.ilike(like)))
    stmt = stmt.order_by(User.subscription_expires_at.desc().nullslast()).limit(min(limit, 400))
    rows = (await db.execute(stmt)).scalars().all()
    return [_user_row(u) for u in rows]


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
async def resolve_report(report_id: str, req: ResolveReq, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
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
    else:
        note = "已標記處理完成"
        r.status = ReportStatus.resolved

    r.resolution = note
    r.resolved_at = datetime.utcnow()
    return {"id": str(r.id), "status": r.status.value, "resolution": note}
