from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from app.database import get_db
from app.models.gathering import Gathering, GatheringMember
from app.models.user import User
from app.services.auth import get_current_user

router = APIRouter(prefix="/api/gatherings", tags=["gatherings"])

GATHERING_TYPES = {"meal", "karaoke", "drinks", "movie"}
VALID_SLOTS = {2, 4, 6, 8}
VALID_HOURS = {2, 6, 12, 24}


class CreateGatheringRequest(BaseModel):
    type: str
    title: str
    location: str
    max_slots: int
    duration_hours: int


def gathering_to_dict(g: Gathering, current_user_id: str = None) -> dict:
    member_list = []
    is_member = False
    for m in (g.members or []):
        member_list.append({
            "id": str(m.user.id),
            "username": m.user.username,
            "display_name": m.user.display_name,
            "avatar_url": m.user.avatar_url or "",
        })
        if str(m.user_id) == current_user_id:
            is_member = True

    return {
        "id": str(g.id),
        "host": {
            "id": str(g.host.id),
            "username": g.host.username,
            "display_name": g.host.display_name,
            "avatar_url": g.host.avatar_url or "",
        },
        "type": g.type,
        "title": g.title,
        "location": g.location,
        "max_slots": g.max_slots,
        "current_slots": g.current_slots,
        "expires_at": g.expires_at.isoformat() if g.expires_at else "",
        "created_at": g.created_at.isoformat() if g.created_at else "",
        "is_active": g.is_active and g.expires_at > datetime.utcnow(),
        "is_host": str(g.host_id) == current_user_id,
        "is_member": is_member or str(g.host_id) == current_user_id,
        "is_full": g.current_slots >= g.max_slots,
        "members": member_list,
    }


@router.get("")
async def list_gatherings(
    type: Optional[str] = Query(None),
    tab: Optional[str] = Query("explore"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()
    query = (
        select(Gathering)
        .options(
            selectinload(Gathering.host),
            selectinload(Gathering.members).selectinload(GatheringMember.user),
        )
    )

    if tab == "mine":
        # My gatherings: ones I host or have joined
        my_gathering_ids = select(GatheringMember.gathering_id).where(
            GatheringMember.user_id == current_user.id
        )
        query = query.where(
            (Gathering.host_id == current_user.id) | (Gathering.id.in_(my_gathering_ids))
        )
    else:
        # Explore: only active and not expired
        query = query.where(
            and_(Gathering.is_active == True, Gathering.expires_at > now)
        )

    if type and type in GATHERING_TYPES:
        query = query.where(Gathering.type == type)

    # Sort by expiry (soonest first for explore, newest first for mine)
    if tab == "mine":
        query = query.order_by(Gathering.created_at.desc())
    else:
        query = query.order_by(Gathering.expires_at.asc())

    result = await db.execute(query)
    gatherings = result.scalars().all()

    return {
        "gatherings": [
            gathering_to_dict(g, str(current_user.id)) for g in gatherings
        ]
    }


@router.post("")
async def create_gathering(
    req: CreateGatheringRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.is_subscribed:
        raise HTTPException(status_code=403, detail="只有付費會員才能發起組局")

    if req.type not in GATHERING_TYPES:
        raise HTTPException(status_code=400, detail="無效的局類型")
    if req.max_slots not in VALID_SLOTS:
        raise HTTPException(status_code=400, detail="人數上限必須是 2/4/6/8")
    if req.duration_hours not in VALID_HOURS:
        raise HTTPException(status_code=400, detail="時效必須是 2/6/12/24 小時")
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="標題不能為空")
    if not req.location.strip():
        raise HTTPException(status_code=400, detail="地點不能為空")

    now = datetime.utcnow()
    gathering = Gathering(
        host_id=current_user.id,
        type=req.type,
        title=req.title.strip(),
        location=req.location.strip(),
        max_slots=req.max_slots,
        current_slots=1,
        expires_at=now + timedelta(hours=req.duration_hours),
        is_active=True,
    )
    db.add(gathering)
    await db.flush()

    # Host is also a member
    member = GatheringMember(
        gathering_id=gathering.id,
        user_id=current_user.id,
    )
    db.add(member)
    await db.flush()

    # Re-fetch with relationships
    result = await db.execute(
        select(Gathering)
        .where(Gathering.id == gathering.id)
        .options(
            selectinload(Gathering.host),
            selectinload(Gathering.members).selectinload(GatheringMember.user),
        )
    )
    gathering = result.scalar_one()
    return gathering_to_dict(gathering, str(current_user.id))


@router.post("/{gathering_id}/join")
async def join_gathering(
    gathering_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.is_subscribed:
        raise HTTPException(status_code=403, detail="只有付費會員才能加入組局")

    result = await db.execute(
        select(Gathering)
        .where(Gathering.id == gathering_id)
        .options(
            selectinload(Gathering.host),
            selectinload(Gathering.members).selectinload(GatheringMember.user),
        )
    )
    gathering = result.scalar_one_or_none()
    if not gathering:
        raise HTTPException(status_code=404, detail="找不到這個局")

    now = datetime.utcnow()
    if not gathering.is_active or gathering.expires_at <= now:
        raise HTTPException(status_code=400, detail="這個局已結束")

    if gathering.current_slots >= gathering.max_slots:
        raise HTTPException(status_code=400, detail="這個局已額滿")

    # Check if already a member
    existing = await db.execute(
        select(GatheringMember).where(
            GatheringMember.gathering_id == gathering.id,
            GatheringMember.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="你已經加入這個局了")

    member = GatheringMember(
        gathering_id=gathering.id,
        user_id=current_user.id,
    )
    db.add(member)
    gathering.current_slots += 1
    db.add(gathering)
    await db.flush()

    # Re-fetch
    result = await db.execute(
        select(Gathering)
        .where(Gathering.id == gathering.id)
        .options(
            selectinload(Gathering.host),
            selectinload(Gathering.members).selectinload(GatheringMember.user),
        )
    )
    gathering = result.scalar_one()
    return gathering_to_dict(gathering, str(current_user.id))


@router.delete("/{gathering_id}/leave")
async def leave_gathering(
    gathering_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Gathering).where(Gathering.id == gathering_id)
    )
    gathering = result.scalar_one_or_none()
    if not gathering:
        raise HTTPException(status_code=404, detail="找不到這個局")

    if str(gathering.host_id) == str(current_user.id):
        raise HTTPException(status_code=400, detail="主揪不能退出自己的局，請使用刪除")

    existing = await db.execute(
        select(GatheringMember).where(
            GatheringMember.gathering_id == gathering.id,
            GatheringMember.user_id == current_user.id,
        )
    )
    member = existing.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=400, detail="你不在這個局裡")

    await db.delete(member)
    gathering.current_slots = max(1, gathering.current_slots - 1)
    db.add(gathering)

    return {"message": "已退出"}


@router.delete("/{gathering_id}")
async def delete_gathering(
    gathering_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Gathering).where(Gathering.id == gathering_id)
    )
    gathering = result.scalar_one_or_none()
    if not gathering:
        raise HTTPException(status_code=404, detail="找不到這個局")

    if str(gathering.host_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="只有主揪可以刪除")

    await db.delete(gathering)
    return {"message": "已刪除"}
