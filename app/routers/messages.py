import os
import uuid as _uuid
import aiofiles
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func, update
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import Optional

from app.database import get_db, async_session
from app.models.message import Message, Conversation
from app.models.user import User
from app.services.auth import get_current_user
from app.services.translate import translate_message
from app.config import UPLOAD_DIR

router = APIRouter(prefix="/api/messages", tags=["messages"])

# Per CLAUDE.md spec: short videos up to 60s / 100MB. Voice clips
# capped looser since they're tiny.
MAX_VIDEO_BYTES = 100 * 1024 * 1024
MAX_AUDIO_BYTES = 25 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}
ALLOWED_AUDIO_EXT = {".webm", ".mp3", ".m4a", ".ogg", ".wav", ".aac"}
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
RECALL_WINDOW = timedelta(hours=1)  # how long after sending the user can still recall


async def _translate_in_background(message_id: str, content: str) -> None:
    """Run translation off the request path and write the result back to the message row.

    Failures are intentionally swallowed — translation is best-effort and must never
    bring down sending. The client polls /chat/{user_id} so the translation will
    appear automatically once it lands.
    """
    try:
        translated = await translate_message(content)
        if not translated or translated == content:
            return
        async with async_session() as session:
            await session.execute(
                update(Message)
                .where(Message.id == message_id)
                .values(translated_content=translated)
            )
            await session.commit()
    except Exception:
        pass


async def _resolve_user_id(db: AsyncSession, identifier: str) -> Optional[str]:
    """Accept either a UUID or username, return user UUID string. None if not found."""
    if not identifier:
        return None
    try:
        _uuid.UUID(identifier)
        # Verify the UUID actually maps to a user
        result = await db.execute(select(User.id).where(User.id == identifier))
        uid = result.scalar_one_or_none()
        if uid:
            return str(uid)
    except (ValueError, TypeError):
        pass
    result = await db.execute(select(User.id).where(User.username == identifier))
    uid = result.scalar_one_or_none()
    return str(uid) if uid else None


class SendMessageRequest(BaseModel):
    receiver_id: str
    content: str
    # Optional id of the message this one is replying to.
    reply_to_id: Optional[str] = None


def _msg_to_dict(m: Message, include_reply: bool = True) -> dict:
    """Serialise a Message row, including reply context and media."""
    if m.is_deleted:
        content = ""
        translated_content = ""
    else:
        content = m.content or ""
        translated_content = (m.translated_content or "")

    base = {
        "id": str(m.id),
        "sender_id": str(m.sender_id),
        "receiver_id": str(m.receiver_id),
        "content": content,
        "translated_content": translated_content,
        "is_read": m.is_read,
        "is_deleted": bool(getattr(m, "is_deleted", False)),
        "media_url": getattr(m, "media_url", "") or "",
        "media_type": getattr(m, "media_type", "") or "",
        "created_at": m.created_at.isoformat(),
    }

    if include_reply:
        reply = getattr(m, "reply_to", None)
        if reply:
            r_content = "" if reply.is_deleted else (reply.content or "")
            base["reply_to"] = {
                "id": str(reply.id),
                "sender_id": str(reply.sender_id),
                "is_deleted": bool(reply.is_deleted),
                "media_type": reply.media_type or "",
                # Short preview only — full content lives in its own row.
                "content_preview": r_content[:80] + ("…" if len(r_content) > 80 else ""),
            }
        else:
            base["reply_to"] = None
    return base


@router.post("/send")
async def send_message(
    req: SendMessageRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify receiver exists (accept UUID or username)
    receiver_uuid = await _resolve_user_id(db, req.receiver_id)
    if not receiver_uuid:
        raise HTTPException(status_code=404, detail="User not found")
    result = await db.execute(select(User).where(User.id == receiver_uuid))
    receiver = result.scalar_one_or_none()
    if not receiver:
        raise HTTPException(status_code=404, detail="User not found")

    # Block guard: refuse if either side has blocked the other
    from app.models.block import BlockedUser
    block_q = await db.execute(
        select(BlockedUser.id).where(
            or_(
                and_(BlockedUser.blocker_id == current_user.id, BlockedUser.blocked_id == receiver.id),
                and_(BlockedUser.blocker_id == receiver.id, BlockedUser.blocked_id == current_user.id),
            )
        )
    )
    if block_q.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="無法傳送訊息給此用戶")

    # Resolve reply_to_id if provided; must point at a real message in this
    # conversation otherwise we ignore it silently.
    reply_to_id = None
    if req.reply_to_id:
        reply_q = await db.execute(
            select(Message).where(
                Message.id == req.reply_to_id,
                or_(
                    and_(Message.sender_id == current_user.id, Message.receiver_id == receiver.id),
                    and_(Message.sender_id == receiver.id, Message.receiver_id == current_user.id),
                ),
            )
        )
        if reply_q.scalar_one_or_none():
            reply_to_id = req.reply_to_id

    # Persist the message first so the client gets an instant response.
    # Translation is dispatched as a background task — DeepL/Google round-trips
    # used to block /send for up to ~5s, locking the UI between sends.
    msg = Message(
        sender_id=current_user.id,
        receiver_id=receiver.id,
        content=req.content,
        translated_content=None,
        reply_to_id=reply_to_id,
    )
    db.add(msg)

    # Update or create conversation
    conv_result = await db.execute(
        select(Conversation).where(
            or_(
                and_(Conversation.user1_id == current_user.id, Conversation.user2_id == receiver.id),
                and_(Conversation.user1_id == receiver.id, Conversation.user2_id == current_user.id),
            )
        )
    )
    conv = conv_result.scalar_one_or_none()
    if conv:
        conv.last_message = req.content
        conv.last_message_at = msg.created_at
        db.add(conv)
    else:
        conv = Conversation(
            user1_id=current_user.id,
            user2_id=receiver.id,
            last_message=req.content,
        )
        db.add(conv)

    await db.flush()
    msg_id_str = str(msg.id)

    # Persist a notification for the receiver (respects their setting)
    try:
        if getattr(receiver, "notify_new_message", True):
            from app.routers.notifications import create_notification
            preview = (req.content or "")[:80]
            await create_notification(
                db,
                user_id=receiver.id,
                n_type="message",
                title=f"{current_user.display_name}:{preview}",
                link=f"/chat/{current_user.id}",
                actor_id=current_user.id,
            )
    except Exception:
        pass

    # Commit before kicking off the background task — the task opens its own session
    # and would race against an in-flight transaction otherwise.
    await db.commit()

    # Skip translation if both users share a nationality — saves a translate
    # API call + DB write that would never produce a useful translation.
    same_nation = (
        getattr(current_user, "nationality", None) is not None
        and getattr(receiver, "nationality", None) is not None
        and current_user.nationality == receiver.nationality
    )
    if not same_nation and req.content:
        background_tasks.add_task(_translate_in_background, msg_id_str, req.content)

    return {
        "id": msg_id_str,
        "content": msg.content,
        "translated_content": "",
        "sender_id": str(msg.sender_id),
        "receiver_id": str(msg.receiver_id),
        "created_at": msg.created_at.isoformat(),
        "reply_to_id": reply_to_id,
        "media_url": "",
        "media_type": "",
        "is_deleted": False,
    }


@router.post("/send-media")
async def send_media_message(
    background_tasks: BackgroundTasks,
    receiver_id: str = Form(...),
    media: UploadFile = File(...),
    media_type: str = Form(...),  # "audio" / "video" / "image"
    content: str = Form(""),
    reply_to_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a chat message that contains an audio / video / image file.
    Text content is optional and accompanies the media."""
    target = await _resolve_user_id(db, receiver_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    result = await db.execute(select(User).where(User.id == target))
    receiver = result.scalar_one_or_none()
    if not receiver:
        raise HTTPException(status_code=404, detail="User not found")

    # Block guard
    from app.models.block import BlockedUser
    block_q = await db.execute(
        select(BlockedUser.id).where(
            or_(
                and_(BlockedUser.blocker_id == current_user.id, BlockedUser.blocked_id == receiver.id),
                and_(BlockedUser.blocker_id == receiver.id, BlockedUser.blocked_id == current_user.id),
            )
        )
    )
    if block_q.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="無法傳送訊息給此用戶")

    media_type = (media_type or "").lower()
    if media_type not in {"audio", "video", "image"}:
        raise HTTPException(status_code=400, detail="media_type 必須是 audio / video / image")

    # Stream-read so we can enforce the per-type cap without buffering the
    # whole file in memory.
    if media_type == "video":
        max_bytes, allowed = MAX_VIDEO_BYTES, ALLOWED_VIDEO_EXT
    elif media_type == "audio":
        max_bytes, allowed = MAX_AUDIO_BYTES, ALLOWED_AUDIO_EXT
    else:  # image
        max_bytes, allowed = MAX_IMAGE_BYTES, ALLOWED_IMAGE_EXT

    ext = os.path.splitext(media.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"格式不支援(允許 {', '.join(sorted(allowed))})")

    chunks = []
    total = 0
    while True:
        chunk = await media.read(1024 * 256)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=400, detail=f"檔案超過 {max_bytes // (1024 * 1024)}MB 上限")
        chunks.append(chunk)

    filename = f"msg_{media_type}_{_uuid.uuid4().hex[:12]}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    async with aiofiles.open(filepath, "wb") as f:
        for c in chunks:
            await f.write(c)
    media_url = f"/uploads/{filename}"

    # Validate reply_to_id if given
    resolved_reply_to = None
    if reply_to_id:
        rq = await db.execute(
            select(Message.id).where(
                Message.id == reply_to_id,
                or_(
                    and_(Message.sender_id == current_user.id, Message.receiver_id == target),
                    and_(Message.sender_id == target, Message.receiver_id == current_user.id),
                ),
            )
        )
        if rq.scalar_one_or_none():
            resolved_reply_to = reply_to_id

    msg = Message(
        sender_id=current_user.id,
        receiver_id=target,
        content=(content or "").strip(),
        translated_content=None,
        reply_to_id=resolved_reply_to,
        media_url=media_url,
        media_type=media_type,
    )
    db.add(msg)

    # Bump conversation
    conv_result = await db.execute(
        select(Conversation).where(
            or_(
                and_(Conversation.user1_id == current_user.id, Conversation.user2_id == target),
                and_(Conversation.user1_id == target, Conversation.user2_id == current_user.id),
            )
        )
    )
    conv = conv_result.scalar_one_or_none()
    label_map = {"audio": "🎤 語音", "video": "🎬 影片", "image": "📷 照片"}
    preview = (content or "").strip() or label_map.get(media_type, "")
    if conv:
        conv.last_message = preview
        conv.last_message_at = msg.created_at
        db.add(conv)
    else:
        db.add(Conversation(
            user1_id=current_user.id, user2_id=target,
            last_message=preview,
        ))

    await db.flush()
    msg_id_str = str(msg.id)
    await db.commit()

    # Same-nationality skip — see /send for rationale
    same_nation_media = (
        getattr(current_user, "nationality", None) is not None
        and getattr(receiver, "nationality", None) is not None
        and current_user.nationality == receiver.nationality
    )
    if msg.content and not same_nation_media:
        background_tasks.add_task(_translate_in_background, msg_id_str, msg.content)

    return {
        "id": msg_id_str,
        "content": msg.content or "",
        "media_url": media_url,
        "media_type": media_type,
        "reply_to_id": resolved_reply_to,
        "is_deleted": False,
        "translated_content": "",
        "sender_id": str(msg.sender_id),
        "receiver_id": str(msg.receiver_id),
        "created_at": msg.created_at.isoformat(),
    }


@router.post("/{message_id}/recall")
async def recall_message(
    message_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a message as recalled. Only the sender can recall, and only
    within RECALL_WINDOW after sending."""
    result = await db.execute(select(Message).where(Message.id == message_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="訊息不存在")
    if str(msg.sender_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="只能收回自己發出的訊息")
    if msg.is_deleted:
        return {"recalled": True, "id": str(msg.id)}
    if datetime.utcnow() - msg.created_at > RECALL_WINDOW:
        raise HTTPException(status_code=400, detail=f"超過 {int(RECALL_WINDOW.total_seconds() // 60)} 分鐘後就無法收回了")

    msg.is_deleted = True
    msg.content = ""
    msg.translated_content = ""
    # Best-effort delete the media file from disk to free space.
    if msg.media_url and msg.media_url.startswith("/uploads/"):
        try:
            os.remove(os.path.join(UPLOAD_DIR, os.path.basename(msg.media_url)))
        except OSError:
            pass
    msg.media_url = ""
    db.add(msg)
    return {"recalled": True, "id": str(msg.id)}


@router.get("/conversations")
async def get_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .where(or_(Conversation.user1_id == current_user.id, Conversation.user2_id == current_user.id))
        .order_by(Conversation.last_message_at.desc())
    )
    convs = result.scalars().all()

    conversations = []
    for c in convs:
        other_id = c.user2_id if str(c.user1_id) == str(current_user.id) else c.user1_id
        other_result = await db.execute(select(User).where(User.id == other_id))
        other = other_result.scalar_one_or_none()
        if not other:
            continue

        # Unread count
        unread_result = await db.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.sender_id == other_id, Message.receiver_id == current_user.id, Message.is_read == False)
        )
        unread = unread_result.scalar()

        conversations.append({
            "id": str(c.id),
            "other_user": {
                "id": str(other.id),
                "username": other.username,
                "display_name": other.display_name,
                "avatar_url": other.avatar_url or "",
                "is_online": other.is_online,
            },
            "last_message": c.last_message,
            "last_message_at": c.last_message_at.isoformat() if c.last_message_at else "",
            "unread_count": unread,
        })

    return {"conversations": conversations}


@router.get("/chat/{user_id}")
async def get_chat_messages(
    user_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Accept UUID or username — resolve to UUID before querying
    target_uuid = await _resolve_user_id(db, user_id)
    if not target_uuid:
        raise HTTPException(status_code=404, detail="User not found")

    # Count unread BEFORE we mark them, so the client can draw a "未讀訊息"
    # divider at the right position on the first open of the chat.
    unread_result = await db.execute(
        select(func.count())
        .select_from(Message)
        .where(
            Message.sender_id == target_uuid,
            Message.receiver_id == current_user.id,
            Message.is_read == False,
        )
    )
    unread_count = unread_result.scalar() or 0

    query = (
        select(Message)
        .where(
            or_(
                and_(Message.sender_id == current_user.id, Message.receiver_id == target_uuid),
                and_(Message.sender_id == target_uuid, Message.receiver_id == current_user.id),
            )
        )
        .options(selectinload(Message.reply_to))
        .order_by(Message.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    messages = result.scalars().all()

    # Mark as read
    await db.execute(
        update(Message)
        .where(Message.sender_id == target_uuid, Message.receiver_id == current_user.id, Message.is_read == False)
        .values(is_read=True)
    )

    return {
        "messages": [_msg_to_dict(m) for m in reversed(messages)],
        "unread_count": unread_count,
    }
