import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
import enum
from sqlalchemy import Enum as SAEnum


class ReportStatus(str, enum.Enum):
    pending = "pending"
    resolved = "resolved"
    dismissed = "dismissed"


class Report(Base):
    """A user-submitted report against another user, a post or a message.

    Required for App Store compliance (objectionable-content reporting).
    Targets are stored generically as (target_type, target_id) so one table
    covers every reportable surface without a column per relationship.
    """
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # SET NULL (not CASCADE) so a report survives if the reporter deletes
    # their account — moderators still need the record.
    reporter_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    target_type = Column(String(20), nullable=False)   # 'user' | 'post' | 'message'
    target_id = Column(UUID(as_uuid=True), nullable=False)
    reason = Column(String(50), default="")            # category key
    detail = Column(Text, default="")                  # free-text description
    status = Column(SAEnum(ReportStatus), default=ReportStatus.pending)
    resolution = Column(String(200), default="")       # what the moderator did
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    reporter = relationship("User", foreign_keys=[reporter_id])
