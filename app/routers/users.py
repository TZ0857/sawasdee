from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, List
from pydantic import BaseModel
import uuid
import os
import aiofiles

from app.database import get_db
from app.models.user import User, Gender
from app.services.auth import get_current_user
from app.config import UPLOAD_DIR

router = APIRouter(prefix="/api/users", tags=["users"])


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = None
    age: Optional[int] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    interests: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    cup_size: Optional[str] = None


def user_to_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "gender": user.gender.value,
        "nationality": user.nationality.value,
        "avatar_url": user.avatar_url or "",
        "cover_url": user.cover_url or "",
        "age": user.age,
        "height": user.height,
        "weight": user.weight,
        "interests": user.interests or "",
        "bio": user.bio or "",
        "location": user.location or "",
        "cup_size": user.cup_size or "",
        "is_subscribed": user.is_subscribed,
        "is_online": user.is_online,
        "created_at": user.created_at.isoformat() if user.created_at else "",
    }


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return user_to_dict(current_user)


@router.put("/me")
async def update_me(
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for field, value in req.dict(exclude_none=True).items():
        setattr(current_user, field, value)
    db.add(current_user)
    return user_to_dict(current_user)


@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ext = os.path.splitext(file.filename)[1] or ".jpg"
    filename = f"avatar_{current_user.id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    async with aiofiles.open(filepath, "wb") as f:
        content = await file.read()
        await f.write(content)

    current_user.avatar_url = f"/uploads/{filename}"
    db.add(current_user)
    return {"avatar_url": current_user.avatar_url}


@router.get("/explore")
async def explore_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    min_age: Optional[int] = None,
    max_age: Optional[int] = None,
    min_height: Optional[float] = None,
    max_height: Optional[float] = None,
    location: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Show opposite gender users: males see Thai females, females see Taiwanese males."""
    if current_user.gender == Gender.male:
        query = select(User).where(User.gender == Gender.female, User.is_active == True)
    else:
        query = select(User).where(User.gender == Gender.male, User.is_active == True)

    # Exclude self
    query = query.where(User.id != current_user.id)

    # Filters
    if min_age is not None:
        query = query.where(User.age >= min_age)
    if max_age is not None:
        query = query.where(User.age <= max_age)
    if min_height is not None:
        query = query.where(User.height >= min_height)
    if max_height is not None:
        query = query.where(User.height <= max_height)
    if location:
        query = query.where(User.location.ilike(f"%{location}%"))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    query = query.order_by(User.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    users = result.scalars().all()

    return {
        "users": [user_to_dict(u) for u in users],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    }


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user_to_dict(user)
