from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ProfileName = Literal["general", "research", "code", "work"]


@dataclass(slots=True)
class HarnessEvent:
    type: str
    raw: dict[str, Any]
    sequence: int | None = None
    thread_id: str | None = None

    @property
    def content(self) -> str:
        value = self.raw.get("content")
        return value if isinstance(value, str) else ""


@dataclass(slots=True)
class SessionBinding:
    app_session_id: str
    profile: ProfileName
    harness_session_id: str
    active_turn_id: str | None = None
    last_sequence: int = 0
    required_actions: list[dict[str, Any]] = field(default_factory=list)
    event_index: dict[str, dict[str, Any]] = field(default_factory=dict)
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "app_session_id": self.app_session_id,
            "profile": self.profile,
            "harness_session_id": self.harness_session_id,
            "active_turn_id": self.active_turn_id,
            "last_sequence": self.last_sequence,
            "required_actions": self.required_actions,
            "event_index": self.event_index,
            "updated_at": self.updated_at,
        }
