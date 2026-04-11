import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
import enum
from sqlalchemy import Enum as SAEnum


class AlbumType(str, enum.Enum):
    public = "public"
    private = "private"


class AccessStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class Album(Base):
    __tablename__ = "albums"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(100), nullable=False)
    album_type = Column(SAEnum(AlbumType), default=AlbumType.public)
    cover_url = Column(String(500), default="")
    photo_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="albums")
    photos = relationship("Photo", back_populates="album", cascade="all, delete-orphan")
    access_requests = relationship("AlbumAccessRequest", back_populates="album", cascade="all, delete-orphan")


class Photo(Base):
    __tablename__ = "photos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    album_id = Column(UUID(as_uuid=True), ForeignKey("albums.id", ondelete="CASCADE"), nullable=False)
    image_url = Column(String(500), nullable=False)
    caption = Column(String(200), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    album = relationship("Album", back_populates="photos")


class AlbumAccessRequest(Base):
    __tablename__ = "album_access_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    album_id = Column(UUID(as_uuid=True), ForeignKey("albums.id", ondelete="CASCADE"), nullable=False)
    requester_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(SAEnum(AccessStatus), default=AccessStatus.pending)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    album = relationship("Album", back_populates="access_requests")
    requester = relationship("User")
