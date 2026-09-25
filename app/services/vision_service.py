import base64
import logging
import re
from typing import Optional

from config import GROQ_API_KEYS, GROQ_VISION_MODEL, VISION_MAX_IMAGE_BYTES

logger = logging.getLogger("J.A.R.V.I.S")

# Known-retired model IDs mapped to a current replacement, so a stale value
# left over in .env doesn't silently break vision.
_DECOMMISSIONED_VISION_MODELS = {
    "llama-3.2-11b-vision-preview": "qwen/qwen3.6-27b",
    "llama-3.2-90b-vision-preview": "qwen/qwen3.6-27b",
    "meta-llama/llama-4-scout-17b-16e-instruct": "qwen/qwen3.6-27b",
    "meta-llama/llama-4-maverick-17b-128e-instruct": "qwen/qwen3.6-27b",
}
_ACTIVE_VISION_MODEL = _DECOMMISSIONED_VISION_MODELS.get(GROQ_VISION_MODEL, GROQ_VISION_MODEL)
if _ACTIVE_VISION_MODEL != GROQ_VISION_MODEL:
    logger.warning(
        "[VISION] GROQ_VISION_MODEL=%s is decommissioned; using %s instead. "
        "Update or remove GROQ_VISION_MODEL in your .env to silence this.",
        GROQ_VISION_MODEL, _ACTIVE_VISION_MODEL,
    )

VISION_SYSTEM_PROMPT = """You are examining a user-provided image, which may come from a camera
or an uploaded photo. Describe it plainly and confidently, and answer the user's question directly.

Guidelines:
- Lead with a direct answer to what was asked, then add a short supporting detail.
- Don't hedge or say you can't see the image unless it is genuinely blank or unreadable.
- If there's readable text, transcribe it. If asked to count objects, give an exact count.
- If asked about position, use left/right/above/below/foreground/background.
- Name specific objects, brands, or products when you can recognize them.
- Keep answers to 1-3 sentences unless more detail is requested.
- Plain text only — no markdown, no emoji, no asterisks."""


class VisionService:
    def __init__(self):
        self._clients = []
        if GROQ_API_KEYS:
            try:
                from groq import Groq
                self._clients = [Groq(api_key=key) for key in GROQ_API_KEYS]
            except Exception as e:
                logger.warning("[VISION] Groq client unavailable: %s", e)

    def analyze(self, image_base64: str, user_question: Optional[str] = None) -> str:
        if not self._clients:
            return "Camera vision isn't available right now — check your GROQ_API_KEY."

        try:
            # Be tolerant of callers that send either raw base64 or a complete
            # browser data URL. The UI currently sends raw JPEG base64.
            if image_base64.startswith("data:") and "," in image_base64:
                image_base64 = image_base64.split(",", 1)[1]
            raw_bytes = base64.b64decode(image_base64, validate=True)
            if len(raw_bytes) > VISION_MAX_IMAGE_BYTES:
                return "That image is too large for me to analyze — try again with a smaller capture."
        except Exception:
            return "I couldn't read that image — please try uploading or capturing it again."

        question = user_question.strip() if user_question else "What do you see?"
        messages = [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }},
                ],
            },
        ]

        last_error = None
        for index, client in enumerate(self._clients):
            try:
                try:
                    # Qwen 3.6 supports an explicit non-thinking mode. Vision
                    # answers are short, so this avoids spending the output
                    # budget on hidden reasoning and returning empty content.
                    resp = client.chat.completions.create(
                        model=_ACTIVE_VISION_MODEL,
                        messages=messages,
                        temperature=0.3,
                        max_completion_tokens=1024,
                        reasoning_effort="none",
                    )
                except TypeError:
                    # Compatibility with an older installed Groq SDK.
                    resp = client.chat.completions.create(
                        model=_ACTIVE_VISION_MODEL,
                        messages=messages,
                        temperature=0.3,
                        max_tokens=1024,
                    )
                text = (resp.choices[0].message.content or "").strip()
                if "<think>" in text:
                    text = re.sub(r"<think>.*?(</think>|$)", "", text, flags=re.DOTALL).strip()
                if text:
                    return text
                last_error = RuntimeError("vision model returned empty content")
                logger.warning("[VISION] Key %s returned empty content; trying failover", index + 1)
            except Exception as e:
                last_error = e
                logger.warning("[VISION] Key %s failed: %s", index + 1, e)

        logger.error("[VISION] Analysis failed on every configured key: %s", last_error)
        return "Something went wrong analyzing the image. Please try again."


_vision_service_singleton = None


def get_vision_service() -> VisionService:
    global _vision_service_singleton
    if _vision_service_singleton is None:
        _vision_service_singleton = VisionService()
    return _vision_service_singleton
