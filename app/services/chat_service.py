import json
import logging
import threading
import uuid
from pathlib import Path
from typing import List, Tuple, Optional

from config import (
    CHATS_DATA_DIR,
    MAX_CHAT_HISTORY_TURNS,
    SESSION_CONTEXT_TOKEN_BUDGET,
    SESSION_RECENT_TOKEN_BUDGET,
    SESSION_SUMMARY_TOKEN_BUDGET,
)
from app.services.context_budget import compact_history

logger = logging.getLogger("J.A.R.V.I.S")


class ChatService:
    """In-memory session cache backed by one JSON file per session on disk,
    so history survives a server restart."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sessions = {}  # session_id -> list[(user, assistant)]
        self._context_stats = {}

    def _path(self, session_id: str) -> Path:
        safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
        return Path(CHATS_DATA_DIR) / f"{safe_id}.json"

    def new_session(self) -> str:
        session_id = uuid.uuid4().hex[:16]
        with self._lock:
            self._sessions[session_id] = []
        return session_id

    def ensure_session(self, session_id: Optional[str]) -> str:
        if session_id and self._load_if_needed(session_id):
            return session_id
        return self.new_session()

    def _load_if_needed(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._sessions:
                return True
        path = self._path(session_id)
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            turns = [(t["user"], t["assistant"]) for t in data.get("turns", [])]
            with self._lock:
                self._sessions[session_id] = turns
            return True
        except Exception as e:
            logger.warning("[CHAT] Could not load session %s: %s", session_id, e)
            return False

    def get_history(self, session_id: str) -> List[Tuple[str, str]]:
        with self._lock:
            return list(self._sessions.get(session_id, []))[-MAX_CHAT_HISTORY_TURNS:]

    def get_model_context(self, session_id: str) -> List[Tuple[str, str]]:
        """Return a bounded session checkpoint plus recent complete turns."""
        with self._lock:
            turns = list(self._sessions.get(session_id, []))
        context, stats = compact_history(
            turns,
            total_budget=SESSION_CONTEXT_TOKEN_BUDGET,
            recent_budget=SESSION_RECENT_TOKEN_BUDGET,
            summary_budget=SESSION_SUMMARY_TOKEN_BUDGET,
        )
        with self._lock:
            self._context_stats[session_id] = stats
        return context

    def get_context_stats(self, session_id: str) -> dict:
        with self._lock:
            stats = dict(self._context_stats.get(session_id, {}))
            turn_count = len(self._sessions.get(session_id, []))
        if not stats and turn_count:
            self.get_model_context(session_id)
            with self._lock:
                stats = dict(self._context_stats.get(session_id, {}))
        return {"session_id": session_id, "stored_turns": turn_count, **stats}

    def append_turn(self, session_id: str, user_msg: str, assistant_msg: str):
        with self._lock:
            self._sessions.setdefault(session_id, []).append((user_msg, assistant_msg))
            turns = self._sessions[session_id]
        self._persist(session_id, turns)

    def _persist(self, session_id: str, turns: List[Tuple[str, str]]):
        try:
            _, checkpoint = compact_history(
                turns,
                total_budget=SESSION_CONTEXT_TOKEN_BUDGET,
                recent_budget=SESSION_RECENT_TOKEN_BUDGET,
                summary_budget=SESSION_SUMMARY_TOKEN_BUDGET,
            )
            payload = {"session_id": session_id, "turns": [
                {"user": u, "assistant": a} for u, a in turns
            ], "context_checkpoint": checkpoint}
            self._path(session_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("[CHAT] Could not persist session %s: %s", session_id, e)

    def list_sessions(self, limit: int = 50) -> List[dict]:
        """Return saved sessions newest-first, with a short preview of the
        first user message, for a chat-history sidebar."""
        results = []
        try:
            files = sorted(
                Path(CHATS_DATA_DIR).glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:limit]
            for f in files:
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    turns = data.get("turns", [])
                    first_user_msg = turns[0]["user"].strip() if turns else ""
                    preview = (first_user_msg[:60] + "…") if len(first_user_msg) > 60 else (first_user_msg or "(empty chat)")
                    results.append({
                        "session_id": data.get("session_id", f.stem),
                        "preview": preview,
                        "turn_count": len(turns),
                        "updated_at": f.stat().st_mtime,
                    })
                except Exception as e:
                    logger.warning("[CHAT] Skipping unreadable session file %s: %s", f, e)
        except Exception as e:
            logger.warning("[CHAT] Could not list sessions: %s", e)
        return results

    def delete_session(self, session_id: str) -> bool:
        """Delete a saved chat's file and drop it from the in-memory cache.
        Returns True if a session was actually removed."""
        removed = False
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                self._context_stats.pop(session_id, None)
                removed = True
        path = self._path(session_id)
        if path.exists():
            try:
                path.unlink()
                removed = True
            except Exception as e:
                logger.warning("[CHAT] Could not delete session file %s: %s", path, e)
        return removed


_chat_service_singleton = None


def get_chat_service() -> ChatService:
    global _chat_service_singleton
    if _chat_service_singleton is None:
        _chat_service_singleton = ChatService()
    return _chat_service_singleton
