import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Notification(Base):
    """Lightweight in-app notification.

    type:
      - 'message'           — new chat message
      - 'like'              — someone liked your post
      - 'comment'           — someone commented on your post
      - 'gathering_request' — someone applied to join your gathering
      - 'gathering_approved'— host approved your application
      - 'gathering_rejected'— host rejected your application
      - 'album_request'     — private-album access request
    link is the in-app URL the bell row should navigate to.
    """
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(40), nullable=False)
    title = Column(String(200), nullable=False, default="")
    body = Column(Text, default="")
    link = Column(String(500), default="")
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
