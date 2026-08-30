"""Local token budgeting, chunking, and extractive session compaction.

This module never calls a model.  It keeps prompt size predictable before a
provider request is made, which protects daily token quotas even when a user
uploads a large source or keeps one session open for a long time.
"""
from __future__ import annotations

import re
import math
from functools import lru_cache
from typing import Iterable, Sequence


@lru_cache(maxsize=1)
def _encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def count_tokens(text: str) -> int:
    value = str(text or "")
    encoder = _encoder()
    if encoder is not None:
        return len(encoder.encode(value, disallowed_special=()))
    # Conservative fallback: punctuation is frequently a token of its own.
    lexical = len(re.findall(r"\w+|[^\w\s]", value, flags=re.UNICODE))
    # Four UTF-8 bytes per token is a deliberately conservative fallback for
    # code, long identifiers, emoji, and non-Latin scripts.
    return max(lexical, math.ceil(len(value.encode("utf-8")) / 4))


def truncate_tokens(text: str, max_tokens: int, *, keep_tail: bool = False) -> str:
    value = str(text or "").strip()
    if max_tokens <= 0 or not value:
        return ""
    encoder = _encoder()
    if encoder is not None:
        tokens = encoder.encode(value, disallowed_special=())
        if len(tokens) <= max_tokens:
            return value
        selected = tokens[-max_tokens:] if keep_tail else tokens[:max_tokens]
        result = encoder.decode(selected).strip()
    else:
        matches = list(re.finditer(r"\w+|[^\w\s]", value, flags=re.UNICODE))
        if count_tokens(value) <= max_tokens:
            return value
        if len(matches) >= max_tokens:
            if keep_tail:
                result = value[matches[-max_tokens].start():].strip()
            else:
                result = value[:matches[max_tokens - 1].end()].strip()
        else:
            result = value
        if count_tokens(result) > max_tokens:
            low, high = 0, len(result)
            while low < high:
                middle = (low + high + 1) // 2
                candidate = result[-middle:] if keep_tail else result[:middle]
                if count_tokens(candidate) <= max_tokens:
                    low = middle
                else:
                    high = middle - 1
            result = (result[-low:] if keep_tail else result[:low]).strip()
    decorated = ("… " + result) if keep_tail else (result + " …")
    while result and count_tokens(decorated) > max_tokens:
        result = (result[1:] if keep_tail else result[:-1]).strip()
        decorated = ("… " + result) if keep_tail else (result + " …")
    return decorated


def chunk_text_tokens(text: str, chunk_tokens: int = 650, overlap_tokens: int = 80) -> list[str]:
    """Split text by tokens while preferring readable paragraph boundaries."""
    value = re.sub(r"\r\n?", "\n", str(text or "")).strip()
    if not value:
        return []
    chunk_tokens = max(80, int(chunk_tokens))
    overlap_tokens = max(0, min(int(overlap_tokens), chunk_tokens // 3))
    encoder = _encoder()
    if encoder is None:
        # The fallback stays token-ish by accumulating sentences/paragraphs.
        units = [item.strip() for item in re.split(r"(?<=\.)\s+|\n{2,}", value) if item.strip()]
        chunks: list[str] = []
        current = ""
        for unit in units:
            if count_tokens(unit) > chunk_tokens:
                if current:
                    chunks.append(current)
                    current = ""
                remaining = unit
                carry = ""
                while remaining:
                    low, high = 1, len(remaining)
                    while low < high:
                        middle = (low + high + 1) // 2
                        candidate = f"{carry}{remaining[:middle]}"
                        if count_tokens(candidate) <= chunk_tokens:
                            low = middle
                        else:
                            high = middle - 1
                    piece = f"{carry}{remaining[:low]}".strip()
                    if not piece:
                        break
                    chunks.append(piece)
                    remaining = remaining[low:].lstrip()
                    carry = truncate_tokens(piece, overlap_tokens, keep_tail=True) + "\n" if remaining and overlap_tokens else ""
                continue
            candidate = f"{current}\n{unit}".strip()
            if current and count_tokens(candidate) > chunk_tokens:
                chunks.append(current)
                current = truncate_tokens(current, overlap_tokens, keep_tail=True) + "\n" + unit
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks

    tokens = encoder.encode(value, disallowed_special=())
    if len(tokens) <= chunk_tokens:
        return [value]
    chunks = []
    start = 0
    while start < len(tokens):
        hard_end = min(len(tokens), start + chunk_tokens)
        end = hard_end
        if hard_end < len(tokens):
            preview = encoder.decode(tokens[start:hard_end])
            # Prefer a paragraph or sentence boundary in the final quarter.
            floor = max(0, int(len(preview) * 0.72))
            candidates = [preview.rfind("\n\n", floor), preview.rfind(". ", floor), preview.rfind("\n", floor)]
            boundary = max(candidates)
            if boundary > 0:
                end = start + len(encoder.encode(preview[: boundary + 1], disallowed_special=()))
        chunk = encoder.decode(tokens[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(tokens):
            break
        start = max(start + 1, end - overlap_tokens)
    return chunks


def compact_history(
    turns: Sequence[tuple[str, str]],
    *,
    total_budget: int = 2200,
    recent_budget: int = 1450,
    summary_budget: int = 650,
) -> tuple[list[tuple[str, str]], dict]:
    """Return an extractive checkpoint plus the newest complete turns.

    Recent turns are preserved verbatim. Older turns become a bounded local
    checkpoint, so compaction consumes zero API tokens of its own.
    """
    values = [(str(user or ""), str(assistant or "")) for user, assistant in turns]
    if not values:
        return [], {"input_turns": 0, "output_turns": 0, "tokens": 0, "compacted_turns": 0}
    recent: list[tuple[str, str]] = []
    used = 0
    split_at = len(values)
    for index in range(len(values) - 1, -1, -1):
        user, assistant = values[index]
        cost = count_tokens(user) + count_tokens(assistant) + 8
        if recent and used + cost > recent_budget:
            break
        if not recent and cost > recent_budget:
            user = truncate_tokens(user, max(100, recent_budget // 3), keep_tail=True)
            assistant = truncate_tokens(assistant, max(180, recent_budget * 2 // 3), keep_tail=True)
            cost = count_tokens(user) + count_tokens(assistant) + 8
        recent.insert(0, (user, assistant))
        used += cost
        split_at = index

    older = values[:split_at]
    checkpoint = ""
    if older:
        lines = []
        # The newest older decisions are generally the most useful.
        for user, assistant in reversed(older):
            user_note = truncate_tokens(re.sub(r"\s+", " ", user), 55)
            assistant_note = truncate_tokens(re.sub(r"\s+", " ", assistant), 85)
            line = f"User: {user_note}\nEDITH: {assistant_note}"
            candidate = "\n\n".join(reversed([line, *lines]))
            if count_tokens(candidate) > summary_budget:
                break
            lines.insert(0, line)
        checkpoint = "Earlier session checkpoint:\n" + "\n\n".join(lines)

    output = list(recent)
    if checkpoint:
        output.insert(0, ("Use this compacted earlier-session context when relevant.", checkpoint))
    # Enforce the total budget after formatting overhead.
    while len(output) > 1 and sum(count_tokens(u) + count_tokens(a) + 8 for u, a in output) > total_budget:
        output.pop(1 if checkpoint else 0)
    tokens = sum(count_tokens(user) + count_tokens(assistant) + 8 for user, assistant in output)
    return output, {
        "input_turns": len(values),
        "output_turns": len(output),
        "tokens": tokens,
        "compacted_turns": len(older),
        "recent_turns": len(recent),
    }


def fit_sections(sections: Iterable[tuple[str, str]], max_tokens: int) -> tuple[str, dict]:
    """Fit labelled sections into a shared budget without splitting labels."""
    remaining = max(0, int(max_tokens))
    selected = []
    original = 0
    for label, body in sections:
        text = str(body or "").strip()
        if not text or remaining <= 0:
            continue
        original += count_tokens(text)
        label_cost = count_tokens(label) + 3
        available = max(0, remaining - label_cost)
        if not available:
            break
        fitted = truncate_tokens(text, available)
        selected.append(f"{label}\n{fitted}")
        remaining -= count_tokens(fitted) + label_cost
    content = "\n\n".join(selected)
    return content, {
        "budget": max_tokens,
        "used": count_tokens(content),
        "original": original,
        "saved": max(0, original - count_tokens(content)),
    }
