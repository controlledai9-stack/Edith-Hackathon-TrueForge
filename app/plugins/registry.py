from __future__ import annotations

from threading import RLock
from typing import Any

from app.plugins.base import Plugin, ToolDefinition, ToolResult
from app.plugins.google_workspace import GmailPlugin, GoogleTasksPlugin, GoogleDrivePlugin, GoogleCalendarPlugin
from app.plugins.browser_operator import BrowserOperatorPlugin
from app.plugins.linkedin import LinkedInPlugin
from app.plugins.marketplace import PluginMarketplace
from app.plugins.local_tools import (
    DocumentsPlugin, FilesPlugin, PDFPlugin,
    PresentationsPlugin, SpreadsheetsPlugin, WebPlugin, TemplateCreatorPlugin,
    VisualizePlugin, SitesPlugin, GitHubPlugin,
    NotebooksPlugin,
    GeminiImagePlugin,
)


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._lock = RLock()

    def register(self, plugin: Plugin) -> None:
        with self._lock: self._plugins[plugin.id] = plugin

    def unregister(self, plugin_id: str) -> None:
        with self._lock: self._plugins.pop(plugin_id, None)

    def get_plugin(self, plugin_id: str) -> Plugin | None:
        return self._plugins.get(plugin_id)

    def list_plugins(self) -> list[dict[str, Any]]:
        return [plugin.metadata() for plugin in self._plugins.values()]

    def enable(self, plugin_id: str, enabled: bool) -> dict[str, Any]:
        plugin = self.get_plugin(plugin_id)
        if not plugin: raise KeyError(plugin_id)
        plugin.enabled = enabled
        return plugin.metadata()

    def disconnect(self, plugin_id: str) -> dict[str, Any]:
        plugin = self.get_plugin(plugin_id)
        if not plugin: raise KeyError(plugin_id)
        plugin.disconnect()
        return plugin.metadata()

    def list_tools(self) -> list[ToolDefinition]:
        result: list[ToolDefinition] = []
        for plugin in self._plugins.values():
            if plugin.enabled and plugin.connected:
                result.extend(plugin.get_tools())
        return result

    def llm_tools(self) -> list[dict[str, Any]]:
        return [tool.llm_schema() for tool in self.list_tools()]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        for plugin in self._plugins.values():
            if not plugin.enabled or not plugin.connected: continue
            for tool in plugin.get_tools():
                if tool.name == tool_name:
                    try: return tool.handler(**arguments)
                    except TypeError as exc: return ToolResult(False, plugin.id, tool_name, error=str(exc), message="Invalid tool arguments")
                    except Exception as exc: return ToolResult(False, plugin.id, tool_name, error=str(exc), message="Tool execution failed")
        return ToolResult(False, "registry", tool_name, error="Tool is unavailable, disabled, or not connected", message="Tool unavailable")


def _build_registry() -> PluginRegistry:
    registry = PluginRegistry()
    browser = BrowserOperatorPlugin()
    for plugin in [DocumentsPlugin(), PDFPlugin(), SpreadsheetsPlugin(), PresentationsPlugin(), TemplateCreatorPlugin(), FilesPlugin(), NotebooksPlugin(), WebPlugin(), GeminiImagePlugin(), LinkedInPlugin(), browser, VisualizePlugin(), SitesPlugin(), GitHubPlugin(), GmailPlugin(), GoogleTasksPlugin(), GoogleDrivePlugin(), GoogleCalendarPlugin()]:
        registry.register(plugin)
    registry.marketplace = PluginMarketplace(registry, browser)
    return registry


_registry = _build_registry()


def get_plugin_registry() -> PluginRegistry:
    return _registry


def get_plugin_marketplace() -> PluginMarketplace:
    return _registry.marketplace
