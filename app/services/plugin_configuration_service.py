from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import set_key

import config


CONFIGURATIONS: dict[str, dict[str, Any]] = {
    "linkedin": {
        "title": "Configure LinkedIn",
        "help": "Create a LinkedIn OAuth app, then add its credentials here. Secrets stay in the local .env file.",
        "fields": [
            {"name": "LINKEDIN_CLIENT_ID", "label": "Client ID", "secret": False, "required": True},
            {"name": "LINKEDIN_CLIENT_SECRET", "label": "Client secret", "secret": True, "required": True},
            {"name": "LINKEDIN_REDIRECT_URI", "label": "Redirect URI", "secret": False, "required": True, "default": "http://localhost:8000/oauth/linkedin/callback"},
        ],
    },
    "google": {
        "title": "Configure Google Workspace",
        "help": "One Google OAuth app connects Gmail, Drive, Calendar, Tasks, and Google Sheets.",
        "fields": [
            {"name": "GOOGLE_CLIENT_ID", "label": "OAuth client ID", "secret": False, "required": True},
            {"name": "GOOGLE_CLIENT_SECRET", "label": "OAuth client secret", "secret": True, "required": True},
            {"name": "GOOGLE_REDIRECT_URI", "label": "Redirect URI", "secret": False, "required": True, "default": "http://localhost:8000/oauth/google/callback"},
        ],
    },
    "browser": {
        "title": "Configure web search",
        "help": "Add a Tavily API key to enable fast structured web search. Public webpage reading works without it.",
        "fields": [{"name": "TAVILY_API_KEY", "label": "Tavily API key", "secret": True, "required": True}],
    },
    "github": {
        "title": "Configure GitHub",
        "help": "A token is optional for public repositories and enables private access when its scopes allow it.",
        "fields": [{"name": "GITHUB_TOKEN", "label": "Personal access token", "secret": True, "required": False}],
    },
    "gemini_image": {
        "title": "Configure Gemini Image",
        "help": "Gemini creates images directly for Work Mode. The fast image model is used by default.",
        "fields": [
            {"name": "GEMINI_API_KEY", "label": "Gemini API key", "secret": True, "required": True},
            {"name": "GEMINI_IMAGE_MODEL", "label": "Image model", "secret": False, "required": True, "default": "gemini-3.1-flash-image"},
        ],
    },
}

ALIASES = {
    "gmail": "google", "google_drive": "google", "google_calendar": "google",
    "google_tasks": "google", "google_sheets": "google",
}


class PluginConfigurationService:
    def __init__(self, env_path: Path | None = None) -> None:
        self.env_path = env_path or (config.BASE_DIR / ".env")

    @staticmethod
    def _configuration_id(plugin_id: str) -> str:
        return ALIASES.get(plugin_id, plugin_id)

    def schema(self, plugin_id: str) -> dict[str, Any]:
        config_id = self._configuration_id(plugin_id)
        definition = CONFIGURATIONS.get(config_id)
        if not definition:
            raise KeyError(plugin_id)
        fields = []
        for field in definition["fields"]:
            name = field["name"]
            fields.append({
                **field,
                "configured": bool(os.getenv(name, "").strip()),
                "value": "" if field.get("secret") else os.getenv(name, "").strip() or field.get("default", ""),
            })
        return {"plugin_id": plugin_id, "configuration_id": config_id, "title": definition["title"], "help": definition["help"], "fields": fields}

    def decorate(self, plugins: list[dict[str, Any]]) -> list[dict[str, Any]]:
        decorated = []
        for plugin in plugins:
            config_id = self._configuration_id(str(plugin.get("id") or ""))
            item = {**plugin, "configurable": config_id in CONFIGURATIONS}
            if item["configurable"]:
                schema = self.schema(str(plugin["id"]))
                item["configuration_complete"] = all(
                    field["configured"] or not field.get("required") for field in schema["fields"]
                )
            decorated.append(item)
        return decorated

    def save(self, plugin_id: str, values: dict[str, Any]) -> dict[str, Any]:
        schema = self.schema(plugin_id)
        allowed = {field["name"]: field for field in schema["fields"]}
        if not isinstance(values, dict):
            raise ValueError("Configuration values must be an object")
        updated: list[str] = []
        for name, raw in values.items():
            field = allowed.get(name)
            if not field:
                raise ValueError(f"Unsupported configuration field: {name}")
            value = str(raw or "").strip()
            if not value and field.get("secret") and os.getenv(name, "").strip():
                continue
            if field.get("required") and not value:
                raise ValueError(f"{field['label']} is required")
            if "\n" in value or "\r" in value or len(value) > 4096:
                raise ValueError(f"{field['label']} contains an invalid value")
            set_key(str(self.env_path), name, value, quote_mode="always")
            os.environ[name] = value
            if hasattr(config, name):
                setattr(config, name, value)
            updated.append(name)

        # Modules that import configuration values directly need an in-process refresh.
        from app.plugins import local_tools
        local_tools.TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
        return {"saved": True, "plugin_id": plugin_id, "updated": updated, "configuration": self.schema(plugin_id)}


plugin_configuration_service = PluginConfigurationService()
