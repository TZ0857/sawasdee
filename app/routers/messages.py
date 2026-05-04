import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func, update
from pydantic import BaseModel
from typing import Optional

from app.database import get_db, async_session
from app.models.message import Message, Conversation
from app.models.user import User
from app.services.auth import get_current_user
from app.services.translate import translate_message

router = APIRouter(prefix="/api/messages", tags=["messages"])


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

    # Persist the message first so the client gets an instant response.
    # Translation is dispatched as a background task — DeepL/Google round-trips
    # used to block /send for up to ~5s, locking the UI between sends.
    msg = Message(
        sender_id=current_user.id,
        receiver_id=receiver.id,
        content=req.content,
        translated_content=None,
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
    # Commit before kicking off the background task — the task opens its own session
    # and would race against an in-flight transaction otherwise.
    await db.commit()

    background_tasks.add_task(_translate_in_background, msg_id_str, req.content)

    return {
        "id": msg_id_str,
        "content": msg.content,
        "translated_content": "",
        "sender_id": str(msg.sender_id),
        "receiver_id": str(msg.receiver_id),
        "created_at": msg.created_at.isoformat(),
    }


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
        "messages": [
            {
                "id": str(m.id),
                "sender_id": str(m.sender_id),
                "receiver_id": str(m.receiver_id),
                "content": m.content,
                "translated_content": m.translated_content or "",
                "is_read": m.is_read,
                "created_at": m.created_at.isoformat(),
            }
            for m in reversed(messages)
        ],
        "unread_count": unread_count,
    }
