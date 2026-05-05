"""Server-side translation cache.

When User A sends a message, no translate API call fires immediately.
The first viewer that taps 翻譯 (or has auto-translate ON) triggers the
real API call; the result is cached here. All subsequent viewers — and
the same viewer revisiting the conversation later — read from this cache
for free.

Works for both 1:1 messages and gathering messages via message_type.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class MessageTranslation(Base):
    __tablename__ = "message_translations"
    __table_args__ = (
        UniqueConstraint("message_type", "message_id", "target_lang",
                         name="uq_msg_translation"),
        Index("ix_msg_translation_lookup", "message_type", "message_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_type = Column(String(20), nullable=False)   # 'chat' or 'gathering'
    message_id = Column(UUID(as_uuid=True), nullable=False)
    target_lang = Column(String(10), nullable=False)    # 'ZH', 'TH', 'EN'
    translated_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
