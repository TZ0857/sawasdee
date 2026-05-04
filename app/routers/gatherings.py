from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone

from app.database import get_db
from app.models.gathering import (
    Gathering, GatheringMember, GatheringRequest, GatheringRequestStatus, GatheringMessage,
)
from app.models.user import User
from app.services.auth import get_current_user

router = APIRouter(prefix="/api/gatherings", tags=["gatherings"])

GATHERING_TYPES = {"meal", "drinks", "karaoke", "movie", "nightlife"}
VALID_SLOTS = {2, 4, 6, 8}

# Acceptable window for the event time (when the actual gathering happens).
EVENT_MIN_LEAD = timedelta(minutes=30)
EVENT_MAX_AHEAD = timedelta(days=30)


class CreateGatheringRequest(BaseModel):
    type: str
    title: str
    location: str
    max_slots: int
    # When the actual meet-up happens (UTC datetime). Doubles as the
    # gathering's expiry — once we hit this time the gathering disappears
    # from the explore feed (you can't sign up for a past event).
    event_at: datetime


class ApplyRequest(BaseModel):
    message: Optional[str] = ""


class ChatMessageRequest(BaseModel):
    content: str


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

    # What's the current viewer's request status for this gathering?
    my_request_status = None
    pending_count = 0  # for hosts
    for r in (g.requests or []):
        if r.status == GatheringRequestStatus.pending:
            pending_count += 1
        if str(r.applicant_id) == current_user_id:
            my_request_status = r.status.value

    event_iso = g.expires_at.isoformat() if g.expires_at else ""
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
        # event_at = when the meet-up actually happens. expires_at kept
        # for backwards compatibility (it always equalled the event time).
        "event_at": event_iso,
        "expires_at": event_iso,
        "created_at": g.created_at.isoformat() if g.created_at else "",
        "is_active": g.is_active and g.expires_at > datetime.utcnow(),
        "is_host": str(g.host_id) == current_user_id,
        "is_member": is_member or str(g.host_id) == current_user_id,
        "is_full": g.current_slots >= g.max_slots,
        "members": member_list,
        # New: status of my application for this specific gathering
        # (None / 'pending' / 'approved' / 'rejected')
        "my_request_status": my_request_status,
        # New: pending request count (only meaningful for the host)
        "pending_request_count": pending_count if str(g.host_id) == current_user_id else 0,
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
            selectinload(Gathering.requests),
        )
    )

    if tab == "mine":
        # My gatherings: ones I host, joined, or have a pending request for
        my_member_ids = select(GatheringMember.gathering_id).where(
            GatheringMember.user_id == current_user.id
        )
        my_request_ids = select(GatheringRequest.gathering_id).where(
            GatheringRequest.applicant_id == current_user.id
        )
        query = query.where(
            (Gathering.host_id == current_user.id)
            | (Gathering.id.in_(my_member_ids))
            | (Gathering.id.in_(my_request_ids))
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
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="標題不能為空")
    if not req.location.strip():
        raise HTTPException(status_code=400, detail="地點不能為空")

    now = datetime.utcnow()
    # Pydantic gives us a tz-aware datetime if the client sent ISO with offset.
    # Normalise to naive UTC so we compare against datetime.utcnow() correctly.
    event_at = req.event_at
    if event_at.tzinfo is not None:
        # Normalise to naive UTC so it matches the rest of the column
        # (which is filled by datetime.utcnow()).
        event_at = event_at.astimezone(timezone.utc).replace(tzinfo=None)

    if event_at < now + EVENT_MIN_LEAD:
        raise HTTPException(status_code=400, detail="局的時間必須至少在 30 分鐘後")
    if event_at > now + EVENT_MAX_AHEAD:
        raise HTTPException(status_code=400, detail="局的時間最多 30 天內")

    gathering = Gathering(
        host_id=current_user.id,
        type=req.type,
        title=req.title.strip(),
        location=req.location.strip(),
        max_slots=req.max_slots,
        current_slots=1,
        expires_at=event_at,
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

    # Re-fetch with relationships. MUST include requests now that
    # gathering_to_dict iterates g.requests — async sessions don't lazy-load.
    result = await db.execute(
        select(Gathering)
        .where(Gathering.id == gathering.id)
        .options(
            selectinload(Gathering.host),
            selectinload(Gathering.members).selectinload(GatheringMember.user),
            selectinload(Gathering.requests),
        )
    )
    gathering = result.scalar_one()
    return gathering_to_dict(gathering, str(current_user.id))


@router.post("/{gathering_id}/apply")
async def apply_to_gathering(
    gathering_id: str,
    req: ApplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit an application to join a gathering. Host must approve to actually join."""
    if not current_user.is_subscribed:
        raise HTTPException(status_code=403, detail="只有付費會員才能申請加入組局")

    result = await db.execute(
        select(Gathering)
        .where(Gathering.id == gathering_id)
        .options(selectinload(Gathering.members), selectinload(Gathering.requests))
    )
    gathering = result.scalar_one_or_none()
    if not gathering:
        raise HTTPException(status_code=404, detail="找不到這個局")

    now = datetime.utcnow()
    if not gathering.is_active or gathering.expires_at <= now:
        raise HTTPException(status_code=400, detail="這個局已結束")

    if str(gathering.host_id) == str(current_user.id):
        raise HTTPException(status_code=400, detail="你是主揪,不需要申請")

    # Already a member?
    if any(str(m.user_id) == str(current_user.id) for m in gathering.members):
        raise HTTPException(status_code=400, detail="你已經在這個局裡了")

    # Already applied?
    existing_req = next(
        (r for r in gathering.requests if str(r.applicant_id) == str(current_user.id)),
        None,
    )
    if existing_req:
        if existing_req.status == GatheringRequestStatus.pending:
            raise HTTPException(status_code=400, detail="你已經申請過,等對方審核中")
        if existing_req.status == GatheringRequestStatus.approved:
            raise HTTPException(status_code=400, detail="你已經被核准了")
        if existing_req.status == GatheringRequestStatus.rejected:
            # Allow re-apply: flip back to pending with the new message
            existing_req.status = GatheringRequestStatus.pending
            existing_req.message = (req.message or "").strip()
            db.add(existing_req)
            await db.flush()
            return {"status": "pending", "message": "已重新送出申請"}

    if gathering.current_slots >= gathering.max_slots:
        raise HTTPException(status_code=400, detail="這個局已額滿")

    new_req = GatheringRequest(
        gathering_id=gathering.id,
        applicant_id=current_user.id,
        message=(req.message or "").strip(),
        status=GatheringRequestStatus.pending,
    )
    db.add(new_req)
    await db.flush()
    return {"status": "pending", "message": "已送出申請,等對方審核"}


@router.get("/requests/incoming")
async def list_incoming_requests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """All pending join requests across the gatherings I host."""
    result = await db.execute(
        select(GatheringRequest)
        .join(Gathering, GatheringRequest.gathering_id == Gathering.id)
        .where(
            Gathering.host_id == current_user.id,
            GatheringRequest.status == GatheringRequestStatus.pending,
        )
        .options(
            selectinload(GatheringRequest.applicant),
            selectinload(GatheringRequest.gathering),
        )
        .order_by(GatheringRequest.created_at.desc())
    )
    requests = result.scalars().all()
    return {
        "requests": [
            {
                "id": str(r.id),
                "gathering": {
                    "id": str(r.gathering.id),
                    "title": r.gathering.title,
                    "type": r.gathering.type,
                },
                "applicant": {
                    "id": str(r.applicant.id),
                    "username": r.applicant.username,
                    "display_name": r.applicant.display_name,
                    "avatar_url": r.applicant.avatar_url or "",
                    "age": r.applicant.age,
                },
                "message": r.message or "",
                "created_at": r.created_at.isoformat(),
            }
            for r in requests
        ],
        "count": len(requests),
    }


@router.get("/requests/pending-count")
async def get_pending_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cheap badge endpoint — returns just the integer count for the navbar."""
    result = await db.execute(
        select(func.count())
        .select_from(GatheringRequest)
        .join(Gathering, GatheringRequest.gathering_id == Gathering.id)
        .where(
            Gathering.host_id == current_user.id,
            GatheringRequest.status == GatheringRequestStatus.pending,
        )
    )
    return {"count": result.scalar() or 0}


@router.post("/requests/{request_id}/approve")
async def approve_request(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Host approves an application: add to members, post system chat, mark approved."""
    result = await db.execute(
        select(GatheringRequest)
        .where(GatheringRequest.id == request_id)
        .options(
            selectinload(GatheringRequest.gathering).selectinload(Gathering.members),
            selectinload(GatheringRequest.applicant),
        )
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="申請不存在")
    if str(req.gathering.host_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="只有主揪可以審核")

    if req.status != GatheringRequestStatus.pending:
        raise HTTPException(status_code=400, detail="這個申請已經處理過了")

    gathering = req.gathering
    if gathering.current_slots >= gathering.max_slots:
        raise HTTPException(status_code=400, detail="這個局已額滿,無法核准")

    # Already a member somehow? (shouldn't happen but defensive)
    if any(str(m.user_id) == str(req.applicant_id) for m in gathering.members):
        req.status = GatheringRequestStatus.approved
        db.add(req)
        return {"status": "approved"}

    member = GatheringMember(gathering_id=gathering.id, user_id=req.applicant_id)
    db.add(member)
    gathering.current_slots += 1
    req.status = GatheringRequestStatus.approved
    db.add(gathering)
    db.add(req)

    # System message in the chat: "{name} 加入了局"
    sys_msg = GatheringMessage(
        gathering_id=gathering.id,
        sender_id=req.applicant_id,
        content=f"{req.applicant.display_name} 加入了局 🎉",
        is_system=True,
    )
    db.add(sys_msg)
    await db.flush()
    return {"status": "approved"}


@router.post("/requests/{request_id}/reject")
async def reject_request(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GatheringRequest)
        .where(GatheringRequest.id == request_id)
        .options(selectinload(GatheringRequest.gathering))
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="申請不存在")
    if str(req.gathering.host_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="只有主揪可以審核")
    if req.status != GatheringRequestStatus.pending:
        raise HTTPException(status_code=400, detail="這個申請已經處理過了")

    req.status = GatheringRequestStatus.rejected
    db.add(req)
    return {"status": "rejected"}


# ----------------------- Gathering chat (group chat per gathering) -----------------------

async def _ensure_member(db, gathering_id: str, user_id: str) -> Gathering:
    result = await db.execute(
        select(Gathering)
        .where(Gathering.id == gathering_id)
        .options(selectinload(Gathering.members), selectinload(Gathering.host))
    )
    gathering = result.scalar_one_or_none()
    if not gathering:
        raise HTTPException(status_code=404, detail="找不到這個局")
    is_host = str(gathering.host_id) == str(user_id)
    is_member = is_host or any(str(m.user_id) == str(user_id) for m in gathering.members)
    if not is_member:
        raise HTTPException(status_code=403, detail="只有局成員才能進入聊天室")
    return gathering


@router.get("/{gathering_id}/messages")
async def list_chat_messages(
    gathering_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    gathering = await _ensure_member(db, gathering_id, str(current_user.id))
    result = await db.execute(
        select(GatheringMessage)
        .where(GatheringMessage.gathering_id == gathering.id)
        .options(selectinload(GatheringMessage.sender))
        .order_by(GatheringMessage.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    msgs = result.scalars().all()
    return {
        "gathering": {
            "id": str(gathering.id),
            "title": gathering.title,
            "type": gathering.type,
        },
        "messages": [
            {
                "id": str(m.id),
                "sender": {
                    "id": str(m.sender.id),
                    "username": m.sender.username,
                    "display_name": m.sender.display_name,
                    "avatar_url": m.sender.avatar_url or "",
                },
                "content": m.content,
                "is_system": m.is_system,
                "created_at": m.created_at.isoformat(),
            }
            for m in reversed(msgs)
        ],
    }


@router.post("/{gathering_id}/messages")
async def send_chat_message(
    gathering_id: str,
    req: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    gathering = await _ensure_member(db, gathering_id, str(current_user.id))
    content = (req.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="訊息不能為空")
    if len(content) > 2000:
        raise HTTPException(status_code=400, detail="訊息過長")

    msg = GatheringMessage(
        gathering_id=gathering.id,
        sender_id=current_user.id,
        content=content,
        is_system=False,
    )
    db.add(msg)
    await db.flush()
    return {
        "id": str(msg.id),
        "content": msg.content,
        "is_system": False,
        "sender_id": str(current_user.id),
        "created_at": msg.created_at.isoformat(),
    }


@router.get("/my-chats")
async def list_my_chats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sidebar list: every gathering I'm a member of (or host of)."""
    my_member_ids = select(GatheringMember.gathering_id).where(
        GatheringMember.user_id == current_user.id
    )
    result = await db.execute(
        select(Gathering)
        .where(
            (Gathering.host_id == current_user.id) | (Gathering.id.in_(my_member_ids))
        )
        .options(
            selectinload(Gathering.host),
            selectinload(Gathering.members),
        )
        .order_by(Gathering.expires_at.desc())
    )
    gatherings = result.scalars().all()
    return {
        "chats": [
            {
                "id": str(g.id),
                "title": g.title,
                "type": g.type,
                "event_at": g.expires_at.isoformat() if g.expires_at else "",
                "is_host": str(g.host_id) == str(current_user.id),
                "member_count": len(g.members),
                "host": {
                    "display_name": g.host.display_name,
                    "avatar_url": g.host.avatar_url or "",
                },
            }
            for g in gatherings
        ]
    }


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
