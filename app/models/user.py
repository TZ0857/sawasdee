import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class Gender(str, enum.Enum):
    male = "male"
    female = "female"


class Nationality(str, enum.Enum):
    taiwanese = "taiwanese"
    thai = "thai"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=False)
    gender = Column(SAEnum(Gender), nullable=False)
    nationality = Column(SAEnum(Nationality), nullable=False)
    avatar_url = Column(String(500), default="")
    cover_url = Column(String(500), default="")

    # Common fields
    age = Column(Integer)
    height = Column(Float)
    weight = Column(Float)
    interests = Column(Text, default="")
    bio = Column(Text, default="")
    location = Column(String(100), default="")

    # Female-specific
    cup_size = Column(String(5), default="")

    # Subscription
    is_subscribed = Column(Boolean, default=False)
    stripe_customer_id = Column(String(255), default="")
    stripe_subscription_id = Column(String(255), default="")
    subscription_expires_at = Column(DateTime, nullable=True)

    # Verification (✓ badge on profiles)
    is_verified = Column(Boolean, default=False)

    # --- Privacy settings (settings page → 隱私設定) ---
    show_online = Column(Boolean, default=True)
    show_last_seen = Column(Boolean, default=True)
    allow_msg_from_non_premium = Column(Boolean, default=True)

    # --- Notification settings (settings page → 通知設定) ---
    notify_new_message = Column(Boolean, default=True)
    notify_likes = Column(Boolean, default=True)
    notify_gatherings = Column(Boolean, default=True)

    # --- Language settings (settings page → 語言設定) ---
    ui_language = Column(String(10), default="zh-TW")
    auto_translate_msgs = Column(Boolean, default=True)

    # Status
    is_active = Column(Boolean, default=True)
    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    posts = relationship("Post", back_populates="author", cascade="all, delete-orphan")
    albums = relationship("Album", back_populates="owner", cascade="all, delete-orphan")
    stories = relationship("Story", back_populates="author", cascade="all, delete-orphan")
    sent_messages = relationship("Message", foreign_keys="Message.sender_id", back_populates="sender")
    received_messages = relationship("Message", foreign_keys="Message.receiver_id", back_populates="receiver")
