from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.database import get_db
from app.models.user import User, Gender, Nationality
from app.services.auth import get_password_hash, verify_password, create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    display_name: str
    gender: Gender
    nationality: Nationality
    age: Optional[int] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    interests: Optional[str] = ""
    bio: Optional[str] = ""
    location: Optional[str] = ""
    cup_size: Optional[str] = ""


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check existing
    result = await db.execute(select(User).where((User.email == req.email) | (User.username == req.username)))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email or username already exists")

    user = User(
        email=req.email,
        username=req.username,
        hashed_password=get_password_hash(req.password),
        display_name=req.display_name,
        gender=req.gender,
        nationality=req.nationality,
        age=req.age,
        height=req.height,
        weight=req.weight,
        interests=req.interests or "",
        bio=req.bio or "",
        location=req.location or "",
        cup_size=req.cup_size or "",
    )
    db.add(user)
    await db.flush()

    token = create_access_token(data={"sub": str(user.id)})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "username": user.username,
            "display_name": user.display_name,
            "gender": user.gender.value,
            "nationality": user.nationality.value,
            "avatar_url": user.avatar_url,
            "is_subscribed": user.is_subscribed,
            "is_admin": getattr(user, "is_admin", False),
        },
    }


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(data={"sub": str(user.id)})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "username": user.username,
            "display_name": user.display_name,
            "gender": user.gender.value,
            "nationality": user.nationality.value,
            "avatar_url": user.avatar_url,
            "is_subscribed": user.is_subscribed,
            "is_admin": getattr(user, "is_admin", False),
        },
    }
