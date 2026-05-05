"""On-demand translation for any text the user picks in the UI.

Used by:
  - 1-on-1 chat (chat.js): "翻譯" action on a message bubble
  - Gathering group chat (gathering_chat.js): same action
  - Anywhere else we want translate-on-tap

This endpoint translates between Chinese (zh-TW) and Thai. English passes
through unchanged. The DB-cached translated_content on Message rows is
written by the background task at send-time, but THIS endpoint is what
the UI calls when the user explicitly taps 翻譯 — so it never depends on
that cache being warm.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.models.user import User
from app.services.auth import get_current_user
from app.services.translate import translate_message, detect_language

router = APIRouter(prefix="/api", tags=["translate"])


class TranslateRequest(BaseModel):
    text: str
    source_lang: Optional[str] = None  # 'TH', 'ZH', or 'EN' — auto-detect if omitted


@router.post("/translate")
async def translate_text(
    req: TranslateRequest,
    current_user: User = Depends(get_current_user),
):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="文字不能為空")
    if len(text) > 4000:
        raise HTTPException(status_code=400, detail="一次最多翻譯 4000 字")
    detected = req.source_lang or detect_language(text)
    translated = await translate_message(text, source_lang=detected)
    return {
        "original": text,
        "translated": translated or text,
        "source_lang": detected,
    }
