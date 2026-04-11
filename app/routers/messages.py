from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func, update
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models.message import Message, Conversation
from app.models.user import User
from app.services.auth import get_current_user
from app.services.translate import translate_message

router = APIRouter(prefix="/api/messages", tags=["messages"])


class SendMessageRequest(BaseModel):
    receiver_id: str
    content: str


@router.post("/send")
async def send_message(
    req: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify receiver exists
    result = await db.execute(select(User).where(User.id == req.receiver_id))
    receiver = result.scalar_one_or_none()
    if not receiver:
        raise HTTPException(status_code=404, detail="User not found")

    # Translate
    translated = await translate_message(req.content)

    msg = Message(
        sender_id=current_user.id,
        receiver_id=receiver.id,
        content=req.content,
        translated_content=translated,
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
    return {
        "id": str(msg.id),
        "content": msg.content,
        "translated_content": msg.translated_content,
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
    query = (
        select(Message)
        .where(
            or_(
                and_(Message.sender_id == current_user.id, Message.receiver_id == user_id),
                and_(Message.sender_id == user_id, Message.receiver_id == current_user.id),
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
        .where(Message.sender_id == user_id, Message.receiver_id == current_user.id, Message.is_read == False)
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
        ]
    }
