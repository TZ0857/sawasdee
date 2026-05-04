import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class GatheringRequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class Gathering(Base):
    __tablename__ = "gatherings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    host_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(20), nullable=False)  # meal, drinks, karaoke, movie, nightlife
    title = Column(String(200), nullable=False)
    location = Column(String(200), nullable=False)
    max_slots = Column(Integer, nullable=False)
    current_slots = Column(Integer, default=1)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    host = relationship("User", foreign_keys=[host_id])
    members = relationship("GatheringMember", back_populates="gathering", cascade="all, delete-orphan")
    requests = relationship("GatheringRequest", back_populates="gathering", cascade="all, delete-orphan")
    messages = relationship("GatheringMessage", back_populates="gathering", cascade="all, delete-orphan")


class GatheringMember(Base):
    __tablename__ = "gathering_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gathering_id = Column(UUID(as_uuid=True), ForeignKey("gatherings.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

    gathering = relationship("Gathering", back_populates="members")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("gathering_id", "user_id", name="uq_gathering_member"),
    )


class GatheringRequest(Base):
    """A user's request to join a gathering. Host approves/rejects."""
    __tablename__ = "gathering_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gathering_id = Column(UUID(as_uuid=True), ForeignKey("gatherings.id", ondelete="CASCADE"), nullable=False)
    applicant_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    message = Column(Text, default="")
    status = Column(SAEnum(GatheringRequestStatus, name="gathering_request_status"),
                    default=GatheringRequestStatus.pending, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    gathering = relationship("Gathering", back_populates="requests")
    applicant = relationship("User")

    __table_args__ = (
        UniqueConstraint("gathering_id", "applicant_id", name="uq_gathering_request"),
    )


class GatheringMessage(Base):
    """Per-gathering group chat. Only members can read/post.
    System messages (e.g. "X 加入了局") have is_system=True and sender_id is the user the message is about."""
    __tablename__ = "gathering_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gathering_id = Column(UUID(as_uuid=True), ForeignKey("gatherings.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    is_system = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    gathering = relationship("Gathering", back_populates="messages")
    sender = relationship("User")
