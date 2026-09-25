from __future__ import annotations

import re
from typing import Any

from app.plugins.registry import get_plugin_registry
from app.services.vector_store import get_memory_store

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations
except ImportError:  # The app still starts before optional dependencies are installed.
    FastMCP = None
    ToolAnnotations = None


registry = get_plugin_registry()
memory = get_memory_store()


def _annotations(read_only: bool, destructive: bool = False):
    if ToolAnnotations is None:
        return None
    return ToolAnnotations(
        readOnlyHint=read_only,
        destructiveHint=destructive,
        idempotentHint=read_only,
        openWorldHint=True,
    )


def _find_tool(tool_name: str):
    return next((tool for tool in registry.list_tools() if tool.name == tool_name), None)


def _adapter_for(tool_name: str, requires_confirmation: bool = False) -> str:
    write_prefixes = ("create_", "add_", "update_", "delete_", "send_", "upload_", "post_", "publish_")
    return "work_execute" if requires_confirmation or tool_name.startswith(write_prefixes) else "plugin_read"


def _execute(tool_name: str, arguments: dict[str, Any], allow_sensitive: bool) -> dict[str, Any]:
    definition = _find_tool(tool_name)
    if definition is None:
        return {"success": False, "error": "Tool is unavailable, disabled, or not connected", "tool": tool_name}
    if definition.requires_confirmation and not allow_sensitive:
        return {"success": False, "error": "This tool must use the approval-gated work_execute adapter", "tool": tool_name}
    return registry.execute(tool_name, arguments).as_dict()


edith_mcp = None
if FastMCP is not None:
    edith_mcp = FastMCP(
        "EDITH Core",
        instructions="Thin adapters over EDITH's existing memory, research, files, browser, and Work Mode capabilities.",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
    )

    @edith_mcp.tool(annotations=_annotations(True))
    def capability_catalog(query: str = "") -> list[dict[str, Any]]:
        """List connected EDITH tool names and short descriptions. Use capability_schema only for the selected tool."""
        words = {word for word in re.findall(r"[a-z0-9]+", query.lower()) if len(word) > 2}
        ranked: list[tuple[int, Any]] = []
        for item in registry.list_tools():
            haystack = f"{item.name} {item.description}".lower()
            score = sum(1 for word in words if word in haystack)
            if not words or score:
                ranked.append((score, item))
        ranked.sort(key=lambda pair: (-pair[0], pair[1].name))
        return [{
            "name": item.name,
            "description": item.description,
            "execute_with": _adapter_for(item.name, item.requires_confirmation),
            "requires_confirmation": item.requires_confirmation,
        } for _, item in ranked[:12]]

    @edith_mcp.tool(annotations=_annotations(True))
    def capability_schema(tool_name: str = "", capability: str = "") -> dict[str, Any]:
        """Return the input schema for one selected EDITH tool."""
        selected = (tool_name or capability).strip()
        if selected in {"work_execute", "plugin_read"}:
            return {
                "success": False,
                "error": f"{selected} is an adapter. Pass the actual EDITH capability name returned by capability_catalog.",
                "example": {"tool_name": "create_document"},
            }
        item = _find_tool(selected)
        if item is None:
            return {"success": False, "error": "Tool is unavailable, disabled, or not connected", "tool": selected}
        return {
            "success": True,
            "name": item.name,
            "description": item.description,
            "parameters": item.parameters,
            "execute_with": _adapter_for(item.name, item.requires_confirmation),
            "requires_confirmation": item.requires_confirmation,
        }

    @edith_mcp.tool(annotations=_annotations(False))
    def create_document(title: str, sections: list[dict[str, Any]], filename: str = "document.docx") -> dict[str, Any]:
        """Create a formatted Word DOCX. Each section may contain heading/title plus paragraphs, bullets, or newline-separated content."""
        return _execute("create_document", {"title": title, "sections": sections, "filename": filename}, True)

    @edith_mcp.tool(annotations=_annotations(False))
    def create_pdf(title: str, sections: list[dict[str, Any]], filename: str = "report.pdf", one_page: bool = False) -> dict[str, Any]:
        """Create a formatted PDF. Set one_page true when the user explicitly requests a one-page report."""
        return _execute("create_pdf", {"title": title, "sections": sections, "filename": filename, "one_page": one_page}, True)

    @edith_mcp.tool(annotations=_annotations(True))
    def memory_search(query: str, max_results: int = 5) -> dict[str, Any]:
        """Search EDITH's local long-term memory and learning documents."""
        return {"query": query, "content": memory.retrieve(query, max(1, min(max_results, 10)))}

    @edith_mcp.tool(annotations=_annotations(True))
    def research_search(query: str, max_results: int = 5) -> dict[str, Any]:
        """Search the public web through EDITH's configured research provider."""
        return _execute("web_search", {"query": query, "max_results": max_results}, False)

    @edith_mcp.tool(annotations=_annotations(True))
    def research_read_url(url: str) -> dict[str, Any]:
        """Read and clean visible text from a public HTTP(S) webpage."""
        return _execute("read_url", {"url": url}, False)

    @edith_mcp.tool(annotations=_annotations(True))
    def files_read(path: str) -> dict[str, Any]:
        """Read a text, CSV, or JSON file inside EDITH's allowed data directory."""
        return _execute("read_file", {"path": path}, False)

    @edith_mcp.tool(annotations=_annotations(True))
    def plugin_read(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run a connected read-only EDITH plugin tool by name."""
        return _execute(tool_name, arguments or {}, False)

    @edith_mcp.tool(annotations=_annotations(False))
    def work_execute(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run a write-capable EDITH Work Mode tool. The harness must obtain approval before this adapter executes."""
        return _execute(tool_name, arguments or {}, True)

    @edith_mcp.tool(annotations=_annotations(False, True))
    def browser_execute(arguments: dict[str, Any]) -> dict[str, Any]:
        """Run a consequential browser task. The harness must obtain explicit user approval first."""
        return _execute("browser_task", arguments, True)
