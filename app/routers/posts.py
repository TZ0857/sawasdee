from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime, timedelta
import uuid
import os
import aiofiles

from app.database import get_db
from app.models.post import Post, Comment, PostLike, Story
from app.models.user import User
from app.services.auth import get_current_user
from app.config import UPLOAD_DIR

router = APIRouter(prefix="/api/posts", tags=["posts"])


def post_to_dict(post: Post, current_user_id=None) -> dict:
    liked = False
    if current_user_id and post.likes:
        liked = any(str(l.user_id) == str(current_user_id) for l in post.likes)
    return {
        "id": str(post.id),
        "author": {
            "id": str(post.author.id),
            "username": post.author.username,
            "display_name": post.author.display_name,
            "avatar_url": post.author.avatar_url or "",
        },
        "content": post.content or "",
        "image_url": post.image_url or "",
        "audio_url": getattr(post, "audio_url", "") or "",
        "likes_count": post.likes_count,
        "comments_count": post.comments_count,
        "is_liked": liked,
        "created_at": post.created_at.isoformat() if post.created_at else "",
    }


@router.post("")
async def create_post(
    content: str = Form(""),
    image: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    content = (content or "").strip()
    image_url = ""
    audio_url = ""

    if image and image.filename:
        ext = os.path.splitext(image.filename)[1].lower() or ".jpg"
        filename = f"post_{uuid.uuid4().hex[:12]}{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(await image.read())
        image_url = f"/uploads/{filename}"

    if audio and audio.filename:
        ext = os.path.splitext(audio.filename)[1].lower() or ".webm"
        filename = f"audio_{uuid.uuid4().hex[:12]}{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(await audio.read())
        audio_url = f"/uploads/{filename}"

    # A post must contain at least one of: text, image, audio.
    if not content and not image_url and not audio_url:
        raise HTTPException(status_code=400, detail="貼文需要文字、照片或語音其中一項")

    post = Post(
        author_id=current_user.id,
        content=content,
        image_url=image_url,
        audio_url=audio_url,
    )
    db.add(post)
    await db.flush()

    result = await db.execute(
        select(Post).where(Post.id == post.id).options(selectinload(Post.author), selectinload(Post.likes))
    )
    post = result.scalar_one()
    return post_to_dict(post, str(current_user.id))


@router.get("/feed")
async def get_feed(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    filter: Optional[str] = Query(None, description="'liked' to only show posts the current user has liked"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.likes))
        .order_by(Post.created_at.desc())
    )

    if filter == "liked":
        # Inner-join PostLike to keep only posts the current user has liked
        query = query.join(PostLike, PostLike.post_id == Post.id).where(
            PostLike.user_id == current_user.id
        )

    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    posts = result.scalars().unique().all()
    return {"posts": [post_to_dict(p, str(current_user.id)) for p in posts]}


@router.post("/{post_id}/like")
async def toggle_like(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    existing = await db.execute(
        select(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == current_user.id)
    )
    like = existing.scalar_one_or_none()

    if like:
        await db.delete(like)
        post.likes_count = max(0, post.likes_count - 1)
        liked = False
    else:
        new_like = PostLike(post_id=post.id, user_id=current_user.id)
        db.add(new_like)
        post.likes_count += 1
        liked = True

    db.add(post)
    return {"liked": liked, "likes_count": post.likes_count}


@router.post("/{post_id}/comments")
async def add_comment(
    post_id: str,
    content: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    comment = Comment(post_id=post.id, author_id=current_user.id, content=content)
    db.add(comment)
    post.comments_count += 1
    db.add(post)
    await db.flush()

    return {
        "id": str(comment.id),
        "content": comment.content,
        "author": {
            "id": str(current_user.id),
            "username": current_user.username,
            "display_name": current_user.display_name,
            "avatar_url": current_user.avatar_url or "",
        },
        "created_at": comment.created_at.isoformat(),
    }


@router.get("/{post_id}/comments")
async def get_comments(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Comment).where(Comment.post_id == post_id)
        .options(selectinload(Comment.author))
        .order_by(Comment.created_at.asc())
    )
    comments = result.scalars().all()
    return {
        "comments": [
            {
                "id": str(c.id),
                "content": c.content,
                "author": {
                    "id": str(c.author.id),
                    "username": c.author.username,
                    "display_name": c.author.display_name,
                    "avatar_url": c.author.avatar_url or "",
                },
                "created_at": c.created_at.isoformat(),
            }
            for c in comments
        ]
    }


# Stories
@router.post("/stories")
async def create_story(
    image: UploadFile = File(...),
    caption: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ext = os.path.splitext(image.filename)[1] or ".jpg"
    filename = f"story_{uuid.uuid4().hex[:12]}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    async with aiofiles.open(filepath, "wb") as f:
        await f.write(await image.read())

    story = Story(
        author_id=current_user.id,
        image_url=f"/uploads/{filename}",
        caption=caption,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.add(story)
    await db.flush()
    return {"id": str(story.id), "image_url": story.image_url, "caption": story.caption}


@router.get("/stories/active")
async def get_active_stories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Story)
        .where(Story.is_active == True, Story.expires_at > datetime.utcnow())
        .options(selectinload(Story.author))
        .order_by(Story.created_at.desc())
    )
    stories = result.scalars().all()

    # Group by author
    authors = {}
    for s in stories:
        aid = str(s.author.id)
        if aid not in authors:
            authors[aid] = {
                "author": {
                    "id": aid,
                    "username": s.author.username,
                    "display_name": s.author.display_name,
                    "avatar_url": s.author.avatar_url or "",
                },
                "stories": [],
            }
        authors[aid]["stories"].append({
            "id": str(s.id),
            "image_url": s.image_url,
            "caption": s.caption,
            "created_at": s.created_at.isoformat(),
        })

    return {"story_groups": list(authors.values())}
