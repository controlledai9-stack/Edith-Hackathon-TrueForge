from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import TRUEFORGE_AGENT_PROFILES, TRUEFORGE_SESSION_MAP
from app.integrations.trueforge.client import TrueForgeClient
from app.integrations.trueforge.types import ProfileName, SessionBinding


logger = logging.getLogger(__name__)


class TrueForgeSessionManager:
    """Persists the app-session ↔ harness-session boundary atomically."""

    def __init__(self, client: TrueForgeClient, path: Path = TRUEFORGE_SESSION_MAP) -> None:
        self.client = client
        self.path = path
        self._lock = threading.RLock()
        self._cache: dict[str, dict[str, Any]] = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(app_session_id: str, profile: ProfileName) -> str:
        return f"{app_session_id}:{profile}"

    def _read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self, data: dict[str, Any]) -> bool:
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        temporary = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        temporary.write_text(payload, encoding="utf-8")
        try:
            # Antivirus, file indexing, and sync clients can briefly open a file
            # without delete sharing on Windows. Retrying keeps a harmless
            # checkpoint write from terminating an otherwise healthy turn.
            for attempt in range(6):
                try:
                    os.replace(temporary, self.path)
                    return True
                except PermissionError:
                    if attempt == 5:
                        break
                    time.sleep(0.03 * (attempt + 1))

            # A non-atomic write is preferable to losing the live harness
            # checkpoint when only destination replacement is blocked.
            try:
                self.path.write_text(payload, encoding="utf-8")
                return True
            except OSError as exc:
                logger.warning("Could not persist TrueForge session map; using memory cache: %s", exc)
                return False
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def get(self, app_session_id: str, profile: ProfileName) -> SessionBinding | None:
        with self._lock:
            key = self._key(app_session_id, profile)
            item = self._cache.get(key) or self._read().get(key)
        if not isinstance(item, dict):
            return None
        try:
            return SessionBinding(**item)
        except TypeError:
            return None

    def save(self, binding: SessionBinding) -> None:
        binding.updated_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            data = self._read()
            data.update(self._cache)
            key = self._key(binding.app_session_id, binding.profile)
            serialized = binding.as_dict()
            self._cache[key] = serialized
            data[key] = serialized
            self._write(data)

    async def get_or_create(self, app_session_id: str, profile: ProfileName) -> SessionBinding:
        existing = self.get(app_session_id, profile)
        if existing:
            return existing
        created = await self.client.create_session(TRUEFORGE_AGENT_PROFILES[profile])
        binding = SessionBinding(app_session_id, profile, str(created["id"]))
        self.save(binding)
        return binding

    def record_event(self, binding: SessionBinding, event: dict[str, Any], sequence: int | None) -> None:
        event_id = event.get("id")
        if isinstance(event_id, str):
            if event.get("type", "").endswith(".delta") and event_id in binding.event_index:
                base = binding.event_index[event_id]
                base["content"] = str(base.get("content") or "") + str(event.get("content") or "")
            else:
                binding.event_index[event_id] = event
        if sequence is not None:
            binding.last_sequence = sequence
        if event.get("type") == "turn.created":
            binding.active_turn_id = event.get("turn_id", event.get("turnId"))
        if event.get("type") == "turn.done":
            state = event.get("state") or {}
            binding.required_actions = state.get("required_actions", state.get("requiredActions", [])) or []
        self.save(binding)
