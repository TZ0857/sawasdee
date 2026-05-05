"""On-demand translation, viewer-relative, with server-side cache.

Used by:
  - 1:1 chat (chat.js) — bubble 🌐 button + auto-translate
  - Gathering group chat (gathering_chat.js) — same

Translates to the VIEWER'S language (derived from current_user.nationality
unless target_lang is explicitly passed). Same-language returns the original
unchanged so the client can detect "no translation needed".

When message_id + message_type are provided, results are cached in
message_translations so the same (message, target_lang) is translated
only once across the system. Group chats with N members of the same
language pay one API call total instead of N.
"""
from typing import Optional
from uuid import UUID as PyUUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database import get_db
from app.models.user import User
from app.models.translation import MessageTranslation
from app.services.auth import get_current_user
from app.services.translate import translate_message, detect_language


router = APIRouter(prefix="/api", tags=["translate"])


def _user_target_lang(user: User) -> str:
    """Map a user's nationality to the language code we translate INTO."""
    nat = getattr(user, "nationality", None)
    val = getattr(nat, "value", str(nat) if nat else "")
    if val == "thai":
        return "TH"
    if val == "taiwanese":
        return "ZH"
    return "EN"   # safe default


class TranslateRequest(BaseModel):
    text: str
    # Optional override; default = viewer's language inferred from User.nationality
    target_lang: Optional[str] = None
    # If supplied, look up / write the translation cache so other viewers
    # don't re-pay for the API call. Without these, translation runs but
    # is NOT cached (used for free-form text translation, e.g. preview).
    message_id: Optional[str] = None
    message_type: Optional[str] = None   # 'chat' or 'gathering'


@router.post("/translate")
async def translate_text(
    req: TranslateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="文字不能為空")
    if len(text) > 4000:
        raise HTTPException(status_code=400, detail="一次最多翻譯 4000 字")

    target = (req.target_lang or _user_target_lang(current_user)).upper()
    source = detect_language(text)

    # Same-language → no translation needed; return early so caller can hide
    # the 翻譯 button or skip rendering a translated bubble.
    if source == target:
        return {
            "original": text,
            "translated": text,
            "source_lang": source,
            "target_lang": target,
            "cached": False,
            "needed": False,
        }

    # Try cache first when a message id is given
    cache_hit = None
    if req.message_id and req.message_type in ("chat", "gathering"):
        try:
            mid = PyUUID(req.message_id)
        except ValueError:
            mid = None
        if mid is not None:
            cached = (await db.execute(
                select(MessageTranslation).where(and_(
                    MessageTranslation.message_type == req.message_type,
                    MessageTranslation.message_id == mid,
                    MessageTranslation.target_lang == target,
                ))
            )).scalar_one_or_none()
            if cached:
                cache_hit = cached.translated_text

    if cache_hit is not None:
        return {
            "original": text,
            "translated": cache_hit,
            "source_lang": source,
            "target_lang": target,
            "cached": True,
            "needed": True,
        }

    # Real translation
    translated = await translate_message(text, source_lang=source)

    # Defensive: reject any fallback-shaped string (legacy "[🇹🇼→🇹🇭] xxx"
    # that older code returned on failure). NEVER cache or surface those.
    looks_like_fallback = (
        translated is not None
        and translated.startswith("[")
        and "→" in translated
    )
    if not translated or looks_like_fallback:
        # Translation API failed — tell the client honestly so the user can
        # retry, but don't poison the cache with placeholder text.
        return {
            "original": text,
            "translated": text,
            "source_lang": source,
            "target_lang": target,
            "cached": False,
            "needed": True,
            "failed": True,
        }

    # Persist cache (best-effort; failure must not break the response)
    if req.message_id and req.message_type in ("chat", "gathering") and translated != text:
        try:
            mid = PyUUID(req.message_id)
            db.add(MessageTranslation(
                message_type=req.message_type,
                message_id=mid,
                target_lang=target,
                translated_text=translated,
            ))
            await db.commit()
        except Exception:
            try: await db.rollback()
            except Exception: pass

    return {
        "original": text,
        "translated": translated,
        "source_lang": source,
        "target_lang": target,
        "cached": False,
        "needed": True,
    }
