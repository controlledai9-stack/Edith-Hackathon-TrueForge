"""
Generates a handful of short "thinking sound" filler clips (e.g. "let me check",
"one sec") using edge-tts, cached to app/audio/starter_N.mp3 so script.js's
PreStarterPlayer has something to play while the first real response streams in.

Invoked automatically by run.py on startup: `python -m app.generate_thinking_audio`.
Safe to run repeatedly — skips files that already exist.
"""
import asyncio
import sys
from pathlib import Path

from config import TTS_VOICE, TTS_RATE, TTS_PITCH, TTS_VOLUME

AUDIO_DIR = Path(__file__).parent / "audio"
STYLE_STAMP = AUDIO_DIR / ".starter_voice_style"
STYLE_KEY = "|".join((TTS_VOICE, TTS_RATE, TTS_PITCH, TTS_VOLUME))

PHRASES = [
    "Let me check that.",
    "One moment.",
    "On it.",
    "Give me a second.",
    "Looking into it now.",
    "Just a moment.",
    "Working on it.",
    "Let me see.",
    "Checking now.",
    "Right away.",
]


async def _generate_one(index: int, text: str, force: bool = False):
    import edge_tts
    out_path = AUDIO_DIR / f"starter_{index}.mp3"
    if out_path.exists() and not force:
        return
    communicate = edge_tts.Communicate(
        text,
        TTS_VOICE,
        rate=TTS_RATE,
        pitch=TTS_PITCH,
        volume=TTS_VOLUME,
    )
    await communicate.save(str(out_path))


async def _generate_all():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    cached_style = STYLE_STAMP.read_text(encoding="utf-8").strip() if STYLE_STAMP.exists() else ""
    force = cached_style != STYLE_KEY
    tasks = [_generate_one(i, phrase, force=force) for i, phrase in enumerate(PHRASES, start=1)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    errors = [result for result in results if isinstance(result, Exception)]
    if errors:
        raise RuntimeError(f"{len(errors)} thinking-audio clip(s) failed") from errors[0]
    STYLE_STAMP.write_text(STYLE_KEY, encoding="utf-8")


def main():
    try:
        asyncio.run(_generate_all())
        print(f"[thinking-audio] Ready ({len(PHRASES)} clips in {AUDIO_DIR})")
    except Exception as e:
        print(f"[thinking-audio] Skipped: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
