from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional
import uuid
import os
import aiofiles

from app.database import get_db
from app.models.album import Album, Photo, AlbumAccessRequest, AlbumType, AccessStatus
from app.models.user import User
from app.services.auth import get_current_user
from app.config import UPLOAD_DIR

router = APIRouter(prefix="/api/albums", tags=["albums"])


@router.post("")
async def create_album(
    title: str = Form(...),
    album_type: str = Form("public"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    album = Album(
        owner_id=current_user.id,
        title=title,
        album_type=AlbumType(album_type),
    )
    db.add(album)
    await db.flush()
    return {
        "id": str(album.id),
        "title": album.title,
        "album_type": album.album_type.value,
        "photo_count": 0,
        "cover_url": "",
    }


@router.get("/user/{user_id}")
async def get_user_albums(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Album).where(Album.owner_id == user_id).options(selectinload(Album.access_requests))
    )
    albums = result.scalars().all()

    album_list = []
    for a in albums:
        is_owner = str(current_user.id) == str(user_id)
        has_access = is_owner

        if a.album_type == AlbumType.private and not is_owner:
            # Check if user has approved access
            for req in a.access_requests:
                if str(req.requester_id) == str(current_user.id) and req.status == AccessStatus.approved:
                    has_access = True
                    break

        album_list.append({
            "id": str(a.id),
            "title": a.title,
            "album_type": a.album_type.value,
            "photo_count": a.photo_count,
            "cover_url": a.cover_url or "",
            "has_access": has_access,
            "is_owner": is_owner,
        })

    return {"albums": album_list}


@router.post("/{album_id}/photos")
async def upload_photo(
    album_id: str,
    image: UploadFile = File(...),
    caption: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Album).where(Album.id == album_id))
    album = result.scalar_one_or_none()
    if not album or str(album.owner_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    ext = os.path.splitext(image.filename)[1] or ".jpg"
    filename = f"photo_{uuid.uuid4().hex[:12]}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    async with aiofiles.open(filepath, "wb") as f:
        await f.write(await image.read())

    photo = Photo(album_id=album.id, image_url=f"/uploads/{filename}", caption=caption)
    db.add(photo)
    album.photo_count += 1
    if not album.cover_url:
        album.cover_url = photo.image_url
    db.add(album)
    await db.flush()

    return {"id": str(photo.id), "image_url": photo.image_url, "caption": photo.caption}


@router.get("/{album_id}/photos")
async def get_album_photos(
    album_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Album).where(Album.id == album_id).options(selectinload(Album.access_requests))
    )
    album = result.scalar_one_or_none()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    is_owner = str(album.owner_id) == str(current_user.id)

    if album.album_type == AlbumType.private and not is_owner:
        has_access = any(
            str(r.requester_id) == str(current_user.id) and r.status == AccessStatus.approved
            for r in album.access_requests
        )
        if not has_access:
            raise HTTPException(status_code=403, detail="Access denied. Request access first.")

    photos_result = await db.execute(
        select(Photo).where(Photo.album_id == album_id).order_by(Photo.created_at.desc())
    )
    photos = photos_result.scalars().all()
    return {
        "photos": [
            {"id": str(p.id), "image_url": p.image_url, "caption": p.caption, "created_at": p.created_at.isoformat()}
            for p in photos
        ]
    }


@router.post("/{album_id}/request-access")
async def request_access(
    album_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Album).where(Album.id == album_id))
    album = result.scalar_one_or_none()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    # Check if already requested
    existing = await db.execute(
        select(AlbumAccessRequest).where(
            AlbumAccessRequest.album_id == album_id,
            AlbumAccessRequest.requester_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already requested")

    req = AlbumAccessRequest(album_id=album.id, requester_id=current_user.id)
    db.add(req)
    await db.flush()
    return {"status": "pending", "message": "Access requested"}


@router.post("/access-requests/{request_id}/approve")
async def approve_access(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AlbumAccessRequest)
        .where(AlbumAccessRequest.id == request_id)
        .options(selectinload(AlbumAccessRequest.album))
    )
    req = result.scalar_one_or_none()
    if not req or str(req.album.owner_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    req.status = AccessStatus.approved
    db.add(req)
    return {"status": "approved"}


@router.post("/access-requests/{request_id}/reject")
async def reject_access(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AlbumAccessRequest)
        .where(AlbumAccessRequest.id == request_id)
        .options(selectinload(AlbumAccessRequest.album))
    )
    req = result.scalar_one_or_none()
    if not req or str(req.album.owner_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    req.status = AccessStatus.rejected
    db.add(req)
    return {"status": "rejected"}


@router.get("/access-requests/pending")
async def get_pending_requests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AlbumAccessRequest)
        .join(Album)
        .where(Album.owner_id == current_user.id, AlbumAccessRequest.status == AccessStatus.pending)
        .options(selectinload(AlbumAccessRequest.requester), selectinload(AlbumAccessRequest.album))
    )
    requests = result.scalars().all()
    return {
        "requests": [
            {
                "id": str(r.id),
                "album": {"id": str(r.album.id), "title": r.album.title},
                "requester": {
                    "id": str(r.requester.id),
                    "username": r.requester.username,
                    "display_name": r.requester.display_name,
                    "avatar_url": r.requester.avatar_url or "",
                },
                "created_at": r.created_at.isoformat(),
            }
            for r in requests
        ]
    }
