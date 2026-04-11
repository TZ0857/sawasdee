import httpx
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


async def translate_message(text: str, source_lang: str = None) -> str:
    """Translate between Thai and Chinese using DeepL or fallback."""
    if not DEEPL_API_KEY:
        # Fallback: return original with a note
        detected = source_lang or detect_language(text)
        if detected == "TH":
            return f"[🇹🇭→🇹🇼 翻譯] {text}"
        elif detected == "ZH":
            return f"[🇹🇼→🇹🇭 แปล] {text}"
        return text

    detected = source_lang or detect_language(text)
    target = "ZH" if detected == "TH" else "TH"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api-free.deepl.com/v2/translate",
                data={
                    "auth_key": DEEPL_API_KEY,
                    "text": text,
                    "target_lang": target,
                },
            )
            if response.status_code == 200:
                result = response.json()
                return result["translations"][0]["text"]
    except Exception:
        pass

    return text
