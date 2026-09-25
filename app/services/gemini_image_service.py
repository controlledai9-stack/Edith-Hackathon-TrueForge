from __future__ import annotations

import base64
import binascii
import mimetypes
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

import config
from app.plugins.utils import ARTIFACTS_DIR, artifact_path


def _verified_reference_part(reference_image_path: str | None) -> dict[str, Any] | None:
    if not reference_image_path:
        return None
    path = Path(reference_image_path).resolve()
    if ARTIFACTS_DIR.resolve() not in path.parents or not path.is_file():
        raise RuntimeError("The previous generated image is no longer available")
    content = path.read_bytes()
    if not content or len(content) > 15_000_000:
        raise RuntimeError("The previous image was empty or exceeded 15 MB")
    mime_type = (mimetypes.guess_type(path.name)[0] or "image/png").lower()
    if not mime_type.startswith("image/"):
        raise RuntimeError("The previous artifact is not an image")
    return {
        "inlineData": {
            "mimeType": mime_type,
            "data": base64.b64encode(content).decode("ascii"),
        }
    }


def _has_image_signature(content: bytes, content_type: str) -> bool:
    signatures = {
        "image/png": (b"\x89PNG\r\n\x1a\n",),
        "image/jpeg": (b"\xff\xd8\xff",),
        "image/jpg": (b"\xff\xd8\xff",),
        "image/webp": (b"RIFF",),
        "image/gif": (b"GIF87a", b"GIF89a"),
    }
    expected = signatures.get(content_type)
    if not expected:
        return bool(content)
    if content_type == "image/webp":
        return content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    return any(content.startswith(signature) for signature in expected)


def generate_gemini_image(
    prompt: str,
    filename_prefix: str = "gemini_image",
    reference_image_path: str | None = None,
) -> tuple[str, dict[str, str]]:
    api_key = config.GEMINI_API_KEY
    model = config.GEMINI_IMAGE_MODEL
    if not api_key:
        raise RuntimeError("Gemini image generation is not configured. Add GEMINI_API_KEY in Plugin Manager.")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        raise RuntimeError("GEMINI_IMAGE_MODEL contains unsupported characters")
    clean_prompt = str(prompt or "").strip()
    if not clean_prompt:
        raise ValueError("An image prompt is required")
    parts: list[dict[str, Any]] = [{"text": clean_prompt}]
    reference_part = _verified_reference_part(reference_image_path)
    if reference_part:
        parts.append(reference_part)
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"aspectRatio": "1:1", "imageSize": "1K"},
            },
        },
        timeout=(10, 180),
    )
    response.raise_for_status()
    payload = response.json()
    inline_data: dict[str, Any] | None = None
    for candidate in payload.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            candidate_data = part.get("inlineData") or part.get("inline_data")
            if isinstance(candidate_data, dict) and candidate_data.get("data"):
                inline_data = candidate_data
                break
        if inline_data:
            break
    if not inline_data:
        reason = str((payload.get("promptFeedback") or {}).get("blockReason") or "").strip()
        suffix = f" ({reason})" if reason else ""
        raise RuntimeError(f"Gemini did not return an image{suffix}")
    content_type = str(inline_data.get("mimeType") or inline_data.get("mime_type") or "image/png").split(";", 1)[0].lower()
    if not content_type.startswith("image/"):
        raise RuntimeError("Gemini returned an unsupported media type")
    try:
        content = base64.b64decode(str(inline_data["data"]), validate=True)
    except (KeyError, ValueError, binascii.Error) as exc:
        raise RuntimeError("Gemini returned invalid image data") from exc
    if not content or len(content) > 15_000_000:
        raise RuntimeError("The generated image was empty or exceeded 15 MB")
    if not _has_image_signature(content, content_type):
        raise RuntimeError("Gemini returned data labelled as an image, but the file was not a valid image")
    extension = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(content_type, "jpg")
    safe_prefix = re.sub(r"[^a-zA-Z0-9_-]+", "_", filename_prefix).strip("_") or "gemini_image"
    filename = f"{safe_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{extension}"
    path = artifact_path(filename, filename, extension)
    path.write_bytes(content)
    return str(path), {"name": path.name, "path": str(path), "mime_type": content_type}


def generate_verified_fallback_image(
    prompt: str,
    filename_prefix: str = "edith_fallback_image",
) -> tuple[str, dict[str, str]]:
    """Generate a new image through the keyless fallback and persist real bytes.

    This is intentionally for new images only. A true edit must retain the
    reference pixels and therefore remains on Gemini's multimodal endpoint.
    """
    clean_prompt = str(prompt or "").strip()
    if not clean_prompt:
        raise ValueError("An image prompt is required")
    encoded = urllib.parse.quote(clean_prompt, safe="")
    response = requests.get(
        f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&model=flux&nologo=true",
        headers={"Accept": "image/png,image/jpeg,image/webp", "User-Agent": "EDITH/1.0"},
        timeout=(10, 180),
    )
    response.raise_for_status()
    content = response.content
    content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
    if content_type not in {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}:
        for candidate in ("image/png", "image/jpeg", "image/webp", "image/gif"):
            if _has_image_signature(content, candidate):
                content_type = candidate
                break
    if content_type not in {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}:
        raise RuntimeError("The fallback image provider returned a non-image response")
    if not content or len(content) > 15_000_000 or not _has_image_signature(content, content_type):
        raise RuntimeError("The fallback image provider did not return a valid image file")
    extension = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(content_type, "jpg")
    safe_prefix = re.sub(r"[^a-zA-Z0-9_-]+", "_", filename_prefix).strip("_") or "edith_fallback_image"
    filename = f"{safe_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{extension}"
    path = artifact_path(filename, filename, extension)
    path.write_bytes(content)
    return str(path), {"name": path.name, "path": str(path), "mime_type": content_type}
