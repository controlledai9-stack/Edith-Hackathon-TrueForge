"""Utilities for converting rich/display answers into natural speech."""

import re


def prepare_tts_text(text: str) -> str:
    """Remove URLs, citation furniture, and markdown while preserving prose."""
    spoken = (text or "").strip()
    if not spoken:
        return ""

    # Markdown links become their human-readable label; bare URLs disappear.
    spoken = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", spoken, flags=re.I)
    spoken = re.sub(
        r"\b(?:see|source|read more at|available at)\s+https?://\S+"
        r"(?:\s+for (?:more )?(?:details|information))?[.!]?",
        "",
        spoken,
        flags=re.I,
    )
    spoken = re.sub(r"https?://\S+", "", spoken, flags=re.I)

    # Source/citation sections are useful on screen but poor spoken output.
    kept_lines = []
    for line in spoken.splitlines():
        clean = line.strip()
        if re.match(r"^(?:sources?|citations?|references?)\s*:?\s*$", clean, re.I):
            break
        if re.match(r"^(?:sources?|citations?)\s*:\s*(?:\[?\d|https?://)", clean, re.I):
            continue
        kept_lines.append(line)
    spoken = "\n".join(kept_lines)

    # Remove citation markers and markdown syntax that TTS engines verbalize.
    spoken = re.sub(r"\[(?:\d+(?:\s*[-,]\s*\d+)*)\]", "", spoken)
    spoken = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", spoken)
    spoken = re.sub(r"[*_`>]", "", spoken)
    spoken = re.sub(r"[ \t]+([,.;:!?])", r"\1", spoken)
    spoken = re.sub(r"[ \t]{2,}", " ", spoken)
    spoken = re.sub(r"(?m)^\s*[.-]\s*$", "", spoken)
    spoken = re.sub(r"\n{3,}", "\n\n", spoken)
    return spoken.strip()
