from __future__ import annotations

from abc import ABC
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable


class PluginState(str, Enum):
    INSTALLED = "INSTALLED"
    CONNECTED = "CONNECTED"
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    ERROR = "ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"


@dataclass
class Artifact:
    name: str
    path: str
    mime_type: str


@dataclass
class ToolResult:
    success: bool
    plugin: str
    tool: str
    data: Any = None
    artifacts: list[Artifact] = field(default_factory=list)
    message: str = ""
    error: str | None = None
    confirmation_required: bool = False

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["artifacts"] = [asdict(item) for item in self.artifacts]
        return result


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., ToolResult]
    requires_confirmation: bool = False

    def llm_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Plugin(ABC):
    id = "plugin"
    name = "Plugin"
    description = ""
    version = "1.0.0"
    requires_auth = False
    permissions: list[str] = []

    def __init__(self) -> None:
        self.enabled = True
        self.error: str | None = None

    @property
    def connected(self) -> bool:
        return not self.requires_auth

    @property
    def state(self) -> PluginState:
        if self.error:
            return PluginState.ERROR
        if not self.enabled:
            return PluginState.DISABLED
        if self.requires_auth and not self.connected:
            return PluginState.AUTH_REQUIRED
        return PluginState.CONNECTED if self.requires_auth else PluginState.ENABLED

    def get_tools(self) -> list[ToolDefinition]:
        return []

    def connect_url(self) -> str | None:
        return None

    def disconnect(self) -> None:
        return None

    def health_check(self) -> dict[str, Any]:
        return {"ok": not bool(self.error), "error": self.error}

    def metadata(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "installed": True,
            "enabled": self.enabled,
            "connected": self.connected,
            "requires_auth": self.requires_auth,
            "permissions": self.permissions,
            "state": self.state.value,
            "connect_url": self.connect_url(),
            "tools": [tool.name for tool in self.get_tools()],
            "error": self.error,
        }
