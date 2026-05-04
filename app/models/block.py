import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class BlockedUser(Base):
    """A blocks B → A never sees B in explore / feed / messages.
    B also cannot DM A or apply to A's gatherings.
    """
    __tablename__ = "blocked_users"
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="uq_block_pair"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    blocker_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    blocked_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
