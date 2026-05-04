"""Block / unblock another user.

A blocks B → A no longer sees B in explore / feed / messages,
and B cannot DM A. Mutual relationship is *not* enforced — B can
still see A's content, but if B tries to message A the send will
be rejected. (Mirrors how IG / Twitter handle blocks.)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from uuid import UUID as PyUUID

from app.database import get_db
from app.models.user import User
from app.models.block import BlockedUser
from app.services.auth import get_current_user

router = APIRouter(prefix="/api/blocks", tags=["blocks"])


def _bu_to_dict(b: BlockedUser, blocked_user: User) -> dict:
    return {
        "id": str(b.id),
        "blocked_user": {
            "id": str(blocked_user.id),
            "username": blocked_user.username,
            "display_name": blocked_user.display_name,
            "avatar_url": blocked_user.avatar_url or "",
        },
        "created_at": b.created_at.isoformat() if b.created_at else "",
    }


@router.get("")
async def list_blocks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List everyone the current user has blocked."""
    result = await db.execute(
        select(BlockedUser, User)
        .join(User, User.id == BlockedUser.blocked_id)
        .where(BlockedUser.blocker_id == current_user.id)
        .order_by(BlockedUser.created_at.desc())
    )
    return {"blocks": [_bu_to_dict(b, u) for b, u in result.all()]}


@router.post("/{user_id}")
async def block_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        target_uuid = PyUUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user id")
    if target_uuid == current_user.id:
        raise HTTPException(status_code=400, detail="不能封鎖自己")
    target = (await db.execute(select(User).where(User.id == target_uuid))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="找不到該用戶")
    # Idempotent — return existing row if already blocked
    existing = (await db.execute(
        select(BlockedUser).where(and_(
            BlockedUser.blocker_id == current_user.id,
            BlockedUser.blocked_id == target_uuid,
        ))
    )).scalar_one_or_none()
    if existing:
        return {"ok": True, "already_blocked": True}
    b = BlockedUser(blocker_id=current_user.id, blocked_id=target_uuid)
    db.add(b)
    await db.flush()
    return {"ok": True, "already_blocked": False}


@router.delete("/{user_id}")
async def unblock_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        target_uuid = PyUUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user id")
    existing = (await db.execute(
        select(BlockedUser).where(and_(
            BlockedUser.blocker_id == current_user.id,
            BlockedUser.blocked_id == target_uuid,
        ))
    )).scalar_one_or_none()
    if existing:
        await db.delete(existing)
    return {"ok": True}


@router.get("/check/{user_id}")
async def check_block(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns {is_blocked: bool} — does current_user block this user?"""
    try:
        target_uuid = PyUUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user id")
    existing = (await db.execute(
        select(BlockedUser.id).where(and_(
            BlockedUser.blocker_id == current_user.id,
            BlockedUser.blocked_id == target_uuid,
        ))
    )).scalar_one_or_none()
    return {"is_blocked": existing is not None}
