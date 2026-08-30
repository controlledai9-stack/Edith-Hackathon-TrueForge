from __future__ import annotations

import json
import re
import secrets
from pathlib import Path
from threading import RLock
from typing import Any

from app.plugins.base import Plugin, ToolDefinition, ToolResult
from app.plugins.browser_operator import BrowserOperatorPlugin
from config import DATA_DIR


CATALOG: list[dict[str, Any]] = [
    {"id": "airtable", "name": "Airtable", "description": "Work with Airtable bases through a confirmed browser workflow.", "homepage": "https://airtable.com/"},
    {"id": "asana", "name": "Asana", "description": "Review and update Asana work through a confirmed browser workflow.", "homepage": "https://app.asana.com/"},
    {"id": "box", "name": "Box", "description": "Access Box files and uploads through a confirmed browser workflow.", "homepage": "https://app.box.com/"},
    {"id": "canva", "name": "Canva", "description": "Create and manage Canva designs through a confirmed browser workflow.", "homepage": "https://www.canva.com/"},
    {"id": "clickup", "name": "ClickUp", "description": "Use ClickUp tasks and documents through a confirmed browser workflow.", "homepage": "https://app.clickup.com/"},
    {"id": "cloudflare", "name": "Cloudflare", "description": "Manage Cloudflare projects through a confirmed browser workflow.", "homepage": "https://dash.cloudflare.com/"},
    {"id": "dropbox", "name": "Dropbox", "description": "Access Dropbox files and uploads through a confirmed browser workflow.", "homepage": "https://www.dropbox.com/home"},
    {"id": "figma", "name": "Figma", "description": "Open and work with Figma projects through a confirmed browser workflow.", "homepage": "https://www.figma.com/files/"},
    {"id": "gamma", "name": "Gamma", "description": "Create Gamma presentations and pages through a confirmed browser workflow.", "homepage": "https://gamma.app/"},
    {"id": "reddit", "name": "Reddit", "description": "Read Reddit and create confirmed posts through the universal browser.", "homepage": "https://www.reddit.com/"},
    {"id": "slack", "name": "Slack", "description": "Read Slack and send confirmed messages through a browser workspace.", "homepage": "https://app.slack.com/"},
    {"id": "spotify", "name": "Spotify", "description": "Open and manage Spotify through a browser workspace.", "homepage": "https://open.spotify.com/"},
    {"id": "todoist", "name": "Todoist", "description": "Manage Todoist tasks through a confirmed browser workflow.", "homepage": "https://app.todoist.com/"},
    {"id": "trello", "name": "Trello", "description": "Review and update Trello boards through a confirmed browser workflow.", "homepage": "https://trello.com/"},
    {"id": "vercel", "name": "Vercel", "description": "Manage Vercel projects and deployments through a confirmed browser workflow.", "homepage": "https://vercel.com/dashboard"},
]


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "objective": {"type": "string"},
            "action_type": {"type": "string", "enum": ["read", "navigate", "login", "upload", "publish", "submit", "edit", "delete", "purchase", "message"]},
            "context": {"type": "string"},
            "file_paths": {"type": "array", "items": {"type": "string"}},
            "confirmed": {"type": "boolean"},
            "confirmation_id": {"type": "string"},
        },
        "required": ["objective", "action_type", "confirmed"],
        "additionalProperties": False,
    }


class MarketplacePlugin(Plugin):
    version = "1.0.0"
    permissions = ["open this provider in the universal browser", "stage external changes only after confirmation"]

    def __init__(self, manifest: dict[str, Any], browser: BrowserOperatorPlugin) -> None:
        super().__init__()
        self.id = str(manifest["id"])
        self.name = str(manifest["name"])
        self.description = str(manifest["description"])
        self.homepage = str(manifest["homepage"])
        self._browser = browser

    @property
    def connected(self) -> bool:
        return self._browser.connected

    def get_tools(self) -> list[ToolDefinition]:
        tool_name = f"{self.id}_browser_task"
        return [ToolDefinition(
            tool_name,
            f"Use {self.name} to complete a website task. External changes require exact confirmation.",
            _schema(),
            self.run,
            requires_confirmation=True,
        )]

    def run(self, objective: str, action_type: str, confirmed: bool = False, context: str = "", file_paths: list[str] | None = None, confirmation_id: str = "") -> ToolResult:
        return self._browser.stage(
            self.homepage, objective, action_type, confirmed=confirmed, file_paths=file_paths,
            context=context, confirmation_id=confirmation_id,
        )


class PluginMarketplace:
    """Curated and manifest-only plugin installation; never executes downloaded code."""

    _PATH = DATA_DIR / "work_mode" / "installed_marketplace_plugins.json"

    def __init__(self, registry: Any, browser: BrowserOperatorPlugin) -> None:
        self.registry = registry
        self.browser = browser
        self._lock = RLock()
        self._manifests = self._load()
        for manifest in self._manifests.values():
            self.registry.register(MarketplacePlugin(manifest, self.browser))

    @staticmethod
    def validate_manifest(manifest: dict[str, Any]) -> dict[str, str]:
        plugin_id = re.sub(r"[^a-z0-9_]+", "_", str(manifest.get("id") or "").strip().lower()).strip("_")
        name = str(manifest.get("name") or "").strip()
        description = str(manifest.get("description") or "").strip()
        homepage = str(manifest.get("homepage") or "").strip()
        if not plugin_id or len(plugin_id) > 48 or not name or not description or not homepage.startswith("https://"):
            raise ValueError("Plugin manifest requires a safe id, name, description, and HTTPS homepage")
        return {"id": plugin_id, "name": name[:80], "description": description[:500], "homepage": homepage[:1000]}

    def _load(self) -> dict[str, dict[str, str]]:
        try:
            payload = json.loads(self._PATH.read_text(encoding="utf-8"))
            return {item["id"]: self.validate_manifest(item) for item in payload if isinstance(item, dict)} if isinstance(payload, list) else {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        self._PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._PATH.with_suffix(f".{secrets.token_hex(4)}.tmp")
        temporary.write_text(json.dumps(list(self._manifests.values()), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self._PATH)

    def catalog(self) -> list[dict[str, Any]]:
        known = {item["id"]: item for item in CATALOG}
        known.update(self._manifests)
        return [{**item, "installed": item["id"] in self._manifests} for item in known.values()]

    def install(self, plugin_id: str) -> dict[str, Any]:
        manifest = next((item for item in CATALOG if item["id"] == plugin_id), None)
        if not manifest:
            raise KeyError(plugin_id)
        return self.install_manifest(manifest)

    def install_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        clean = self.validate_manifest(manifest)
        with self._lock:
            if self.registry.get_plugin(clean["id"]):
                raise ValueError("A plugin with this id is already installed")
            self._manifests[clean["id"]] = clean
            self.registry.register(MarketplacePlugin(clean, self.browser))
            self._save()
        return self.registry.get_plugin(clean["id"]).metadata()
