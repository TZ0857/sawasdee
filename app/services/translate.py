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
    """Translate between Thai and Chinese. Tries DeepL first, then Google Translate."""
    detected = source_lang or detect_language(text)

    if detected == "EN":
        return text

    # Map language codes for translation
    if detected == "TH":
        target_label = "zh-TW"
        source_label = "th"
        flag = "🇹🇭→🇹🇼"
    else:
        target_label = "th"
        source_label = "zh-TW"
        flag = "🇹🇼→🇹🇭"

    # Try DeepL first
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
                    return result["translations"][0]["text"]
        except Exception:
            pass

    # Fallback: Google Translate (free)
    translated = await google_translate_free(text, source_label, target_label)
    if translated and translated != text:
        return translated

    # Last resort: return with language label
    return f"[{flag}] {text}"
