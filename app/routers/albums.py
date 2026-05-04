from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import Optional, List
import uuid
import os
import aiofiles

from app.database import get_db
from app.models.album import Album, Photo, AlbumAccessRequest, AlbumType, AccessStatus
from app.models.user import User
from app.services.auth import get_current_user
from app.config import UPLOAD_DIR

router = APIRouter(prefix="/api/albums", tags=["albums"])

MAX_PHOTOS_PER_ALBUM = 20  # CLAUDE.md spec


class UpdateAlbumRequest(BaseModel):
    title: Optional[str] = None
    album_type: Optional[str] = None
    cover_photo_id: Optional[str] = None  # set this photo as the album cover


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
    # Resolve username → id if user_id isn't a UUID
    target_id = user_id
    try:
        uuid.UUID(user_id)
    except (ValueError, TypeError):
        ures = await db.execute(select(User.id).where(User.username == user_id))
        u = ures.scalar_one_or_none()
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        target_id = str(u)

    result = await db.execute(
        select(Album).where(Album.owner_id == target_id).options(selectinload(Album.access_requests))
    )
    albums = result.scalars().all()

    album_list = []
    for a in albums:
        is_owner = str(current_user.id) == str(target_id)
        has_access = is_owner
        request_status = None  # for the viewer: None / 'pending' / 'approved' / 'rejected'

        if a.album_type == AlbumType.private and not is_owner:
            for req in a.access_requests:
                if str(req.requester_id) == str(current_user.id):
                    request_status = req.status.value
                    if req.status == AccessStatus.approved:
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
            "request_status": request_status,
        })

    return {"albums": album_list}


@router.put("/{album_id}")
async def update_album(
    album_id: str,
    req: UpdateAlbumRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner-only: rename, switch public/private, or set cover photo."""
    result = await db.execute(select(Album).where(Album.id == album_id))
    album = result.scalar_one_or_none()
    if not album or str(album.owner_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    if req.title is not None:
        album.title = req.title.strip() or album.title
    if req.album_type is not None:
        try:
            album.album_type = AlbumType(req.album_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="album_type must be public or private")
    if req.cover_photo_id is not None:
        photo_res = await db.execute(
            select(Photo).where(Photo.id == req.cover_photo_id, Photo.album_id == album.id)
        )
        photo = photo_res.scalar_one_or_none()
        if not photo:
            raise HTTPException(status_code=404, detail="Photo not in this album")
        album.cover_url = photo.image_url

    db.add(album)
    return {
        "id": str(album.id),
        "title": album.title,
        "album_type": album.album_type.value,
        "cover_url": album.cover_url or "",
        "photo_count": album.photo_count,
    }


@router.delete("/{album_id}")
async def delete_album(
    album_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner-only: delete the album and cascade to its photos/requests."""
    result = await db.execute(select(Album).where(Album.id == album_id))
    album = result.scalar_one_or_none()
    if not album or str(album.owner_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")
    await db.delete(album)
    return {"deleted": True}


@router.delete("/photos/{photo_id}")
async def delete_photo(
    photo_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner-only: remove a photo. Recompute photo_count and clear cover if needed."""
    result = await db.execute(
        select(Photo).where(Photo.id == photo_id).options(selectinload(Photo.album))
    )
    photo = result.scalar_one_or_none()
    if not photo or str(photo.album.owner_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    album = photo.album
    cover_being_deleted = (album.cover_url == photo.image_url)
    photo_url = photo.image_url
    await db.delete(photo)
    album.photo_count = max(0, album.photo_count - 1)
    if cover_being_deleted:
        # Pick another remaining photo as cover, else clear it.
        remaining = await db.execute(
            select(Photo).where(Photo.album_id == album.id, Photo.id != photo_id).limit(1)
        )
        next_photo = remaining.scalar_one_or_none()
        album.cover_url = next_photo.image_url if next_photo else ""
    db.add(album)

    # Best-effort delete the file on disk too (may fail silently if Volume re-attached differently)
    if photo_url and photo_url.startswith("/uploads/"):
        try:
            os.remove(os.path.join(UPLOAD_DIR, os.path.basename(photo_url)))
        except OSError:
            pass

    return {"deleted": True, "photo_count": album.photo_count}


@router.post("/{album_id}/photos")
async def upload_photo(
    album_id: str,
    image: UploadFile = File(...),
    caption: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner-only single-photo upload. Use /upload-batch for multiple files."""
    result = await db.execute(select(Album).where(Album.id == album_id))
    album = result.scalar_one_or_none()
    if not album or str(album.owner_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    if album.photo_count >= MAX_PHOTOS_PER_ALBUM:
        raise HTTPException(
            status_code=400,
            detail=f"相簿最多 {MAX_PHOTOS_PER_ALBUM} 張照片,請先刪除一些",
        )

    ext = os.path.splitext(image.filename or "")[1].lower() or ".jpg"
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


@router.post("/{album_id}/photos/batch")
async def upload_photos_batch(
    album_id: str,
    images: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner-only multi-photo upload. Stops at the 20-photo cap."""
    result = await db.execute(select(Album).where(Album.id == album_id))
    album = result.scalar_one_or_none()
    if not album or str(album.owner_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    available = MAX_PHOTOS_PER_ALBUM - album.photo_count
    if available <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"相簿已達 {MAX_PHOTOS_PER_ALBUM} 張上限,請先刪除一些",
        )

    accepted = images[:available]
    skipped = max(0, len(images) - available)
    uploaded = []
    for image in accepted:
        if not image.filename:
            continue
        ext = os.path.splitext(image.filename)[1].lower() or ".jpg"
        filename = f"photo_{uuid.uuid4().hex[:12]}{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(await image.read())
        photo = Photo(album_id=album.id, image_url=f"/uploads/{filename}", caption="")
        db.add(photo)
        album.photo_count += 1
        if not album.cover_url:
            album.cover_url = photo.image_url
        uploaded.append({"image_url": photo.image_url})

    db.add(album)
    await db.flush()
    return {"uploaded": uploaded, "skipped": skipped, "photo_count": album.photo_count}


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
