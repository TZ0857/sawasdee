import asyncio
import httpx
import json
import urllib.parse
from app.config import DEEPL_API_KEY


def detect_language(text: str) -> str:
    """Simple language detection based on character ranges."""
    for char in text:
        code = ord(char)
        # Thai Unicode range
        if 0x0E00 <= code <= 0x0E7F:
            return "TH"
        # CJK Unified Ideographs (Chinese)
        if 0x4E00 <= code <= 0x9FFF:
            return "ZH"
    return "EN"


async def google_translate_free(text: str, source: str, target: str) -> str:
    """Free Google Translate API (unofficial but widely used)."""
    try:
        encoded = urllib.parse.quote(text)
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={source}&tl={target}&dt=t&q={encoded}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                result = response.json()
                translated = ''.join(part[0] for part in result[0] if part[0])
                return translated
    except Exception:
        pass
    return None


async def translate_message(text: str, source_lang: str = None) -> str:
    """Translate between Thai and Chinese. Tries DeepL first, then Google Translate.

    Returns None when both providers fail. The caller (router) treats None
    as 'translation unavailable right now' — it does NOT cache anything,
    so a transient API failure can be retried later by the user.
    """
    detected = source_lang or detect_language(text)

    if detected == "EN":
        return text

    if detected == "TH":
        target_label, source_label = "zh-TW", "th"
    else:
        target_label, source_label = "th", "zh-TW"

    # Try DeepL first (paid, more accurate)
    if DEEPL_API_KEY:
        try:
            target_deepl = "ZH" if detected == "TH" else "TH"
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    "https://api-free.deepl.com/v2/translate",
                    data={
                        "auth_key": DEEPL_API_KEY,
                        "text": text,
                        "target_lang": target_deepl,
                    },
                )
                if response.status_code == 200:
                    result = response.json()
                    out = result.get("translations", [{}])[0].get("text")
                    if out and out.strip() and out != text:
                        return out
        except Exception:
            pass

    # Fallback: Google Translate (free, less reliable)
    # Retry once with a short backoff — common case is rate-limit / transient 5xx.
    for attempt in range(2):
        translated = await google_translate_free(text, source_label, target_label)
        if translated and translated.strip() and translated != text:
            return translated
        await asyncio.sleep(0.4)

    # Both providers failed — return None so the caller doesn't cache
    # a fake "[🇹🇼→🇹🇭] originaltext" placeholder as a real translation.
    return None
