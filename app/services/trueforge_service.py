from __future__ import annotations

import base64
import json
import mimetypes
import re
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from config import (
    TRUEFORGE_ENABLED,
    TRUEFORGE_CODE_SANDBOX_ENABLED,
    TRUEFORGE_FALLBACK_ENABLED,
    TRUEFORGE_MCP_URL,
)
from app.integrations.trueforge.client import TrueForgeClient, TrueForgeError
from app.integrations.trueforge.profiles import bootstrap_trueforge
from app.integrations.trueforge.session_manager import TrueForgeSessionManager
from app.integrations.trueforge.types import ProfileName, SessionBinding


DIRECT_LOCAL_PATTERNS = (
    r"^(?:open|play|launch)\b",
    r"^(?:scrape|extract data|get data|collect data|pull data)\b",
    r"^(?:monitor|stop monitoring|show (?:my )?watchlist|scan (?:all|my))\b",
    r"^(?:add|create|set|remove|delete|complete)\s+(?:a\s+)?(?:task|reminder|timer|alarm)\b",
)
CODE_HINT = re.compile(
    r"\b(?:code|program|debug|bug|refactor|repository|repo|unit test|pytest|npm|typescript|javascript|python|html|css|api endpoint)\b",
    re.I,
)
FAST_WORK_APP_ACTION = re.compile(
    r"(?:\b(?:post|publish|share|upload|submit|send|message|read|check|list|create|add|update|delete)\b.{0,180}"
    r"\b(?:linkedin|reddit|instagram|facebook|twitter|medium|wordpress|youtube|gmail|google\s+(?:drive|calendar|tasks?))\b|"
    r"\b(?:linkedin|reddit|instagram|facebook|twitter|medium|wordpress|youtube|gmail|google\s+(?:drive|calendar|tasks?))\b.{0,180}"
    r"\b(?:post|publish|share|upload|submit|send|message|read|check|list|create|add|update|delete)\b|"
    r"\b(?:generate|genrate|create|make|design|draw)\b.{0,70}\b(?:image|photo|picture|graphic|visual)\b)",
    re.I,
)


class TrueForgeService:
    def __init__(self) -> None:
        self.client = TrueForgeClient()
        self.sessions = TrueForgeSessionManager(self.client)
        self._health_cache: tuple[float, dict[str, Any]] = (0.0, {"ok": False})

    @property
    def enabled(self) -> bool:
        return TRUEFORGE_ENABLED

    @property
    def fallback_enabled(self) -> bool:
        return TRUEFORGE_FALLBACK_ENABLED

    async def health(self, refresh: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        stamp, cached = self._health_cache
        if not refresh and now - stamp < 10:
            return {**cached, "enabled": self.enabled, "cached": True}
        result = await self.client.health() if self.enabled else {"ok": False, "reason": "disabled"}
        self._health_cache = (now, result)
        return {**result, "enabled": self.enabled, "cached": False}

    def profile_for(self, mode: str, research_branch: str, message: str) -> ProfileName:
        if mode == "work":
            return "work"
        if mode == "research":
            return "research"
        if CODE_HINT.search(message):
            return "code"
        return "general"

    def should_route(self, mode: str, message: str, has_pending_work_action: bool = False) -> bool:
        if not self.enabled or has_pending_work_action:
            return False
        # Ordinary Edit-mode conversation should stay on EDITH's low-latency
        # streaming engine. TrueForge is reserved for orchestrated Work and
        # Research turns where its multi-tool harness adds value.
        if mode in {"edit", "research"}:
            return False
        if any(re.search(pattern, message, re.I) for pattern in DIRECT_LOCAL_PATTERNS):
            return False
        if mode == "work" and FAST_WORK_APP_ACTION.search(message):
            return False
        if CODE_HINT.search(message) and not TRUEFORGE_CODE_SANDBOX_ENABLED:
            return False
        return True

    @staticmethod
    def _data_uri(value: str, index: int) -> tuple[str, str]:
        if value.startswith("data:"):
            mime = value[5:].split(";", 1)[0] or "application/octet-stream"
            return f"attachment-{index}{mimetypes.guess_extension(mime) or ''}", value
        try:
            raw = base64.b64decode(value, validate=False)
        except Exception:
            raw = b""
        mime = "image/png" if raw.startswith(b"\x89PNG") else "image/jpeg"
        return f"attachment-{index}{mimetypes.guess_extension(mime) or '.bin'}", f"data:{mime};base64,{value}"

    def message_input(self, message: str, images: list[str]) -> list[dict[str, Any]]:
        if not images:
            return [{"type": "user.message", "content": message}]
        parts: list[dict[str, Any]] = [{"type": "text", "text": message}]
        for index, item in enumerate(images[:8], 1):
            name, data = self._data_uri(item, index)
            parts.append({"type": "file", "name": name, "data": data})
        return [{"type": "user.message", "content": parts}]

    def _approval_payload(self, binding: SessionBinding, event: dict[str, Any]) -> dict[str, Any]:
        calls = []
        refs = event.get("tool_calls", event.get("toolCalls", [])) or []
        for ref in refs:
            source_id = ref.get("source_event_id", ref.get("sourceEventId"))
            message = binding.event_index.get(str(source_id), {})
            candidates = message.get("tool_calls", message.get("toolCalls", [])) or []
            call = next((item for item in candidates if item.get("id") == ref.get("id")), {})
            info = call.get("tool_info", call.get("toolInfo", {})) or {}
            function = call.get("function", {}) or {}
            raw_arguments = function.get("arguments") or "{}"
            display_name = info.get("name") or function.get("name") or "tool"
            try:
                parsed_arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            except json.JSONDecodeError:
                parsed_arguments = raw_arguments
            if isinstance(parsed_arguments, dict) and display_name == "call_tool":
                adapter_name = parsed_arguments.get("tool_name") or "tool"
                adapter_input = parsed_arguments.get("input") or {}
                inner_name = adapter_input.get("tool_name") if isinstance(adapter_input, dict) else None
                display_name = f"{adapter_name} → {inner_name}" if inner_name else str(adapter_name)
                raw_arguments = json.dumps(adapter_input, ensure_ascii=False, indent=2)
                parsed_arguments = adapter_input
            calls.append({
                "tool_call_id": ref.get("id"),
                "thread_id": event.get("thread_id", event.get("threadId")),
                "tool_name": display_name,
                "arguments": raw_arguments,
                "summary": self._approval_summary(display_name, parsed_arguments),
            })
        return {"type": "tool_approval", "calls": calls}

    @staticmethod
    def _approval_summary(tool_name: str, arguments: Any) -> dict[str, Any]:
        """Build a compact, human-readable description without changing gated arguments."""
        values = arguments if isinstance(arguments, dict) else {}
        effective_name = tool_name.split("→")[-1].strip()
        if isinstance(values.get("input"), dict):
            effective_name = str(values.get("tool_name") or effective_name)
            values = values["input"]

        labels = {
            "create_pdf": "Create PDF",
            "create_document": "Create Word document",
            "create_text_file": "Create text file",
            "create_excel": "Create Excel workbook",
            "create_presentation": "Create presentation",
            "create_notebook": "Create notebook",
        }
        summary: dict[str, Any] = {
            "label": labels.get(effective_name, effective_name.replace("_", " ").strip().title() or "Run tool"),
            "items": [],
        }
        items: list[dict[str, str]] = summary["items"]
        if values.get("filename"):
            items.append({"label": "File", "value": str(values["filename"])})
        if values.get("title"):
            items.append({"label": "Title", "value": str(values["title"])})

        sections = values.get("sections")
        if isinstance(sections, list):
            lines = 0
            preview = ""
            for section in sections:
                if not isinstance(section, dict):
                    continue
                paragraphs = section.get("paragraphs") or section.get("content") or []
                if isinstance(paragraphs, str):
                    section_lines = [line.strip() for line in paragraphs.splitlines() if line.strip()]
                elif isinstance(paragraphs, list):
                    section_lines = [str(line).strip() for line in paragraphs if str(line).strip()]
                else:
                    section_lines = []
                lines += len(section_lines)
                if not preview and section_lines:
                    preview = section_lines[0]
            description = f"{len(sections)} section{'s' if len(sections) != 1 else ''}"
            if lines:
                description += f" · {lines} line{'s' if lines != 1 else ''}"
            items.append({"label": "Content", "value": description})
            if preview:
                summary["preview"] = preview[:220]
        elif values.get("content"):
            content = str(values["content"])
            line_count = len([line for line in content.splitlines() if line.strip()])
            items.append({"label": "Content", "value": f"{line_count or 1} line{'s' if line_count != 1 else ''}"})
            summary["preview"] = next((line.strip() for line in content.splitlines() if line.strip()), content)[:220]
        return summary

    @staticmethod
    def _decode_arguments(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    def _referenced_calls(self, binding: SessionBinding, event: dict[str, Any]) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        for ref in event.get("tool_calls", event.get("toolCalls", [])) or []:
            source_id = str(ref.get("source_event_id", ref.get("sourceEventId")) or "")
            source = binding.event_index.get(source_id, {})
            candidates = source.get("tool_calls", source.get("toolCalls", [])) or []
            call = next((item for item in candidates if item.get("id") == ref.get("id")), {})
            if call:
                calls.append(call)
        return calls

    def _response_tool_name(self, binding: SessionBinding, event: dict[str, Any]) -> str:
        tool_call_id = event.get("tool_call_id", event.get("toolCallId"))
        for source in binding.event_index.values():
            for call in source.get("tool_calls", source.get("toolCalls", [])) or []:
                if call.get("id") != tool_call_id:
                    continue
                function = call.get("function", {}) or {}
                name = str(function.get("name") or "tool")
                arguments = self._decode_arguments(function.get("arguments") or "{}")
                if name == "call_tool" and isinstance(arguments, dict):
                    return str(arguments.get("tool_name") or name)
                return name
        return "tool"

    def _question_payload(self, binding: SessionBinding, event: dict[str, Any]) -> dict[str, Any]:
        questions: list[dict[str, Any]] = []
        for call in self._referenced_calls(binding, event):
            function = call.get("function", {}) or {}
            arguments = self._decode_arguments(function.get("arguments") or "{}")
            question = "The agent needs more information before it can continue."
            options: list[str] = []
            if isinstance(arguments, dict):
                question = str(arguments.get("question") or question)
                raw_options = arguments.get("options") or []
                options = [str(item) for item in raw_options if isinstance(item, (str, int, float))]
            questions.append({
                "tool_call_id": call.get("id"),
                "thread_id": event.get("thread_id", event.get("threadId")) or "main",
                "question": question,
                "options": options,
            })
        return {"type": "tool_response", "questions": questions}

    @staticmethod
    def _artifact_payload(event: dict[str, Any]) -> list[dict[str, str]]:
        content: Any = event.get("content")
        content = TrueForgeService._decode_arguments(content)
        if isinstance(content, dict) and isinstance(content.get("structuredContent"), dict):
            content = content["structuredContent"]
        candidates = content.get("artifacts", []) if isinstance(content, dict) else []
        artifacts: list[dict[str, str]] = []
        for item in candidates if isinstance(candidates, list) else []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or Path(str(item.get("path") or "")).name)
            if not name:
                continue
            artifacts.append({
                "name": name,
                "mime_type": str(item.get("mime_type") or item.get("mimeType") or "application/octet-stream"),
                **({"url": str(item["url"])} if item.get("url") else {}),
            })
        return artifacts

    async def _merge_turn_events(self, binding: SessionBinding) -> None:
        if not binding.active_turn_id:
            return
        for merged in await self.client.list_turn_events(binding.harness_session_id, binding.active_turn_id):
            self.sessions.record_event(binding, merged, None)

    async def _present_required_event(self, binding: SessionBinding, event: HarnessEvent) -> dict[str, Any] | None:
        if event.type in {"tool.approval_required", "tool.response_required"}:
            await self._merge_turn_events(binding)
        if event.type == "tool.approval_required":
            return {"approval": self._approval_payload(binding, event.raw)}
        if event.type == "tool.response_required":
            return {"question": self._question_payload(binding, event.raw)}
        if event.type == "mcp.auth_required":
            return {"auth_required": event.raw.get("mcp_servers", event.raw.get("mcpServers", []))}
        return None

    async def _continue_turn(
        self, binding: SessionBinding, input_items: list[dict[str, Any]] | None
    ) -> AsyncGenerator[dict[str, Any], None]:
        async for event in self.client.stream_turn(binding.harness_session_id, input_items):
            self.sessions.record_event(binding, event.raw, event.sequence)
            if event.type == "model.message.delta" and event.thread_id in (None, "main") and event.content:
                yield {"chunk": event.content}
            elif event.type == "tool.response":
                artifacts = self._artifact_payload(event.raw)
                if artifacts:
                    yield {"artifacts": artifacts}
                tool_name = self._response_tool_name(binding, event.raw)
                if tool_name not in {"list_tools", "get_tool_info", "capability_catalog", "capability_schema"}:
                    yield {"activity": {
                        "event": "tool_completed",
                        "message": f"{tool_name.replace('_', ' ').title()} completed.",
                        "tool": tool_name,
                        "thread_id": event.thread_id,
                    }}
            elif event.type in {"tool.approval_required", "tool.response_required", "mcp.auth_required"}:
                presented = await self._present_required_event(binding, event)
                if presented:
                    yield presented
            elif event.type == "thread.created":
                yield {"activity": {"event": "subagent_started", "message": event.raw.get("title") or "Parallel step started", "thread_id": event.thread_id}}
            elif event.type == "thread.done":
                yield {"activity": {"event": "subagent_completed", "message": event.raw.get("title") or "Parallel step completed", "thread_id": event.thread_id}}
            elif event.type == "turn.done":
                state = event.raw.get("state") or {}
                if state.get("status") == "error":
                    raise TrueForgeError(str(state.get("message") or "TrueForge turn failed"))
                yield {"harness": {"event": "turn.done", "status": state.get("status"), "required_actions": binding.required_actions}}

    async def stream(
        self,
        app_session_id: str,
        profile: ProfileName,
        message: str,
        images: list[str],
    ) -> AsyncGenerator[dict[str, Any], None]:
        binding = await self.sessions.get_or_create(app_session_id, profile)
        yield {"activity": {"event": "harness_session", "message": f"TrueForge · {profile.title()} profile", "session_id": binding.harness_session_id}}
        async for item in self._continue_turn(binding, self.message_input(message, images)):
            yield item

    async def approve(
        self,
        app_session_id: str,
        profile: ProfileName,
        tool_call_id: str,
        thread_id: str,
        allow: bool,
        reason: str = "",
    ) -> AsyncGenerator[dict[str, Any], None]:
        binding = self.sessions.get(app_session_id, profile)
        if not binding:
            raise KeyError("No TrueForge session is mapped to this chat")
        if not allow:
            # In EDITH, Deny means stop the current task. Sending a normal
            # denial back to the model lets it continue via another route.
            await self.client.cancel(binding.harness_session_id)
            binding.required_actions = []
            self.sessions.save(binding)
            yield {"activity": {
                "event": "tool_denied",
                "message": "Action denied. The current task was stopped.",
                "tool_call_id": tool_call_id,
            }}
            yield {"harness": {"event": "turn.cancelled", "status": "cancelled"}}
            return
        approval: dict[str, Any] = {"status": "allow" if allow else "deny"}
        if reason:
            approval["reason"] = reason
        item = {
            "type": "user.tool_approval",
            "thread_id": thread_id,
            "tool_call_id": tool_call_id,
            "approval": approval,
        }
        async for output in self._continue_turn(binding, [item]):
            yield output

    async def respond(
        self, app_session_id: str, profile: ProfileName, tool_call_id: str, thread_id: str, content: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        binding = self.sessions.get(app_session_id, profile)
        if not binding:
            raise KeyError("No TrueForge session is mapped to this chat")
        item = {"type": "user.tool_response", "thread_id": thread_id, "tool_call_id": tool_call_id, "content": content}
        async for output in self._continue_turn(binding, [item]):
            yield output

    async def resume_auth(
        self, app_session_id: str, profile: ProfileName
    ) -> AsyncGenerator[dict[str, Any], None]:
        binding = self.sessions.get(app_session_id, profile)
        if not binding:
            raise KeyError("No TrueForge session is mapped to this chat")
        async for output in self._continue_turn(binding, None):
            yield output

    async def resume(
        self, app_session_id: str, profile: ProfileName
    ) -> AsyncGenerator[dict[str, Any], None]:
        binding = self.sessions.get(app_session_id, profile)
        if not binding or not binding.active_turn_id:
            raise KeyError("No resumable TrueForge turn is mapped to this chat")
        turn = await self.client.get_turn(binding.harness_session_id, binding.active_turn_id)
        state = turn.get("state") or {}
        if state.get("status") == "running":
            async for event in self.client.subscribe_turn(binding.harness_session_id, binding.active_turn_id, binding.last_sequence):
                self.sessions.record_event(binding, event.raw, event.sequence)
                if event.type == "model.message.delta" and event.thread_id in (None, "main") and event.content:
                    yield {"chunk": event.content}
                elif event.type in {"tool.approval_required", "tool.response_required", "mcp.auth_required"}:
                    presented = await self._present_required_event(binding, event)
                    if presented:
                        yield presented
                elif event.type == "turn.done":
                    yield {"harness": {"event": "turn.done", "status": (event.raw.get("state") or {}).get("status")}}
            return
        await self._merge_turn_events(binding)
        required = state.get("required_actions", state.get("requiredActions", [])) or binding.required_actions
        for raw in required:
            event = HarnessEvent(str(raw.get("type") or "unknown"), raw, None, raw.get("thread_id", raw.get("threadId")))
            presented = await self._present_required_event(binding, event)
            if presented:
                yield presented
        yield {"harness": {"event": "turn.done", "status": state.get("status"), "required_actions": required}}

    async def retry_rate_limited(
        self, app_session_id: str, profile: ProfileName
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Resume a running turn or continue an errored rate-limited turn safely."""
        binding = self.sessions.get(app_session_id, profile)
        if not binding or not binding.active_turn_id:
            raise KeyError("No rate-limited TrueForge turn is mapped to this chat")
        turn = await self.client.get_turn(binding.harness_session_id, binding.active_turn_id)
        state = turn.get("state") or {}
        status = str(state.get("status") or "")
        if status == "running":
            async for output in self.resume(app_session_id, profile):
                yield output
            return
        error_text = str(state.get("message") or state.get("error") or "")
        if status not in {"error", "failed"} and "429" not in error_text and "rate limit" not in error_text.lower():
            raise TrueForgeError(error_text or f"The previous turn ended with status '{status or 'unknown'}'")
        continuation = [{
            "type": "user.message",
            "content": (
                "Continue the interrupted task from where it stopped. Do not repeat completed tool actions. "
                "Reuse existing results and artifacts. Ask for approval again before every write or consequential action."
            ),
        }]
        async for output in self._continue_turn(binding, continuation):
            yield output

    async def cancel(self, app_session_id: str, profile: ProfileName) -> dict[str, Any]:
        binding = self.sessions.get(app_session_id, profile)
        if not binding:
            raise KeyError("No TrueForge session is mapped to this chat")
        return await self.client.cancel(binding.harness_session_id)

    async def bootstrap(self) -> dict[str, Any]:
        return await bootstrap_trueforge(self.client, TRUEFORGE_MCP_URL)


_service: TrueForgeService | None = None


def get_trueforge_service() -> TrueForgeService:
    global _service
    if _service is None:
        _service = TrueForgeService()
    return _service
