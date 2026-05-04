import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


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
