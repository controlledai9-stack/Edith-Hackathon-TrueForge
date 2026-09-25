from __future__ import annotations

import json
from typing import Any, AsyncGenerator

import httpx

from config import TRUEFORGE_BASE_URL, TRUEFORGE_TIMEOUT_SECONDS, TRUEFORGE_TOKEN
from app.integrations.trueforge.types import HarnessEvent


class TrueForgeError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class TrueForgeClient:
    """Small async adapter around the pinned TrueForge HTTP/SSE contract."""

    def __init__(
        self,
        base_url: str = TRUEFORGE_BASE_URL,
        token: str = TRUEFORGE_TOKEN,
        timeout_seconds: float = TRUEFORGE_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = httpx.Timeout(timeout_seconds, connect=1.0)

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = {**self.headers, **kwargs.pop("headers", {})}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
        if response.is_error:
            try:
                detail = response.json().get("error", {}).get("message") or response.text
            except Exception:
                detail = response.text
            raise TrueForgeError(detail or f"TrueForge returned HTTP {response.status_code}", response.status_code)
        if not response.content:
            return {}
        payload = response.json()
        return payload.get("data", payload)

    async def health(self) -> dict[str, Any]:
        errors: list[str] = []
        for path in ("/api/v1/capabilities", "/health"):
            try:
                data = await self._request("GET", path)
                return {"ok": True, "base_url": self.base_url, "data": data}
            except Exception as exc:
                errors.append(str(exc))
        return {"ok": False, "base_url": self.base_url, "error": errors[-1] if errors else "unreachable"}

    async def create_session(self, agent_name: str) -> dict[str, Any]:
        return await self._request("POST", "/api/v1/sessions", json={"agent": {"name": agent_name}})

    async def get_turn(self, session_id: str, turn_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/sessions/{session_id}/turns/{turn_id}")

    async def list_turn_events(self, session_id: str, turn_id: str) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/api/v1/sessions/{session_id}/turns/{turn_id}/events")
        items = data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
        return [item.get("event", item) for item in items if isinstance(item, dict)]

    async def cancel(self, session_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/api/v1/sessions/{session_id}/cancel")

    async def upsert_mcp_server(self, name: str, url: str, description: str) -> dict[str, Any]:
        manifest = {
            "name": name,
            "description": description,
            "type": "remote",
            "url": url,
        }
        return await self._request("PUT", "/api/v1/settings/mcp-servers", json={"manifest": manifest})

    async def upsert_openai_compatible_provider(
        self,
        name: str,
        base_url: str,
        api_key: str,
        model_id: str,
        model_name: str,
        context_length: int = 131072,
        max_output_tokens: int = 32768,
    ) -> dict[str, Any]:
        manifest = {
            "type": "custom",
            "name": name,
            "base_url": base_url,
            "auth": {"api_key": api_key},
            "models": [{
                "model_id": model_id,
                "name": model_name,
                "properties": {
                    "context_length": context_length,
                    "max_output_tokens": max_output_tokens,
                },
            }],
        }
        return await self._request("PUT", "/api/v1/settings/model-providers", json={"manifest": manifest})

    async def list_agents(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/api/v1/agents")
        return data if isinstance(data, list) else data.get("data", [])

    async def create_agent(self, name: str, manifest: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/api/v1/agents", json={"name": name, "manifest": manifest})

    async def update_agent(self, agent_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", f"/api/v1/agents/{agent_id}", json={"manifest": manifest})

    async def stream_turn(
        self,
        session_id: str,
        input_items: list[dict[str, Any]] | None = None,
        previous_turn_id: str = "auto",
    ) -> AsyncGenerator[HarnessEvent, None]:
        payload: dict[str, Any] = {"previous_turn_id": previous_turn_id, "stream": True}
        if input_items is not None:
            payload["input"] = input_items
        headers = {**self.headers, "Accept": "text/event-stream", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/v1/sessions/{session_id}/turns",
                headers=headers,
                json=payload,
            ) as response:
                if response.is_error:
                    body = await response.aread()
                    raise TrueForgeError(body.decode("utf-8", "replace"), response.status_code)
                event_id: int | None = None
                data_lines: list[str] = []
                async for line in response.aiter_lines():
                    if line.startswith("id:"):
                        try:
                            event_id = int(line[3:].strip())
                        except ValueError:
                            event_id = None
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                    elif line == "" and data_lines:
                        raw_text = "\n".join(data_lines)
                        data_lines = []
                        try:
                            raw = json.loads(raw_text)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
                            raw = raw["data"]
                        if not isinstance(raw, dict):
                            continue
                        yield HarnessEvent(
                            type=str(raw.get("type") or "unknown"),
                            raw=raw,
                            sequence=event_id,
                            thread_id=raw.get("thread_id", raw.get("threadId")),
                        )
                        event_id = None

    async def subscribe_turn(
        self, session_id: str, turn_id: str, after_sequence: int = 0
    ) -> AsyncGenerator[HarnessEvent, None]:
        params = {"after_sequence_number": after_sequence}
        headers = {**self.headers, "Accept": "text/event-stream"}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            async with client.stream(
                "GET",
                f"{self.base_url}/api/v1/sessions/{session_id}/turns/{turn_id}/subscribe",
                headers=headers,
                params=params,
            ) as response:
                if response.is_error:
                    raise TrueForgeError((await response.aread()).decode("utf-8", "replace"), response.status_code)
                event_id: int | None = None
                async for line in response.aiter_lines():
                    if line.startswith("id:"):
                        try: event_id = int(line[3:].strip())
                        except ValueError: event_id = None
                    elif line.startswith("data:"):
                        try: raw = json.loads(line[5:].lstrip())
                        except json.JSONDecodeError: continue
                        if isinstance(raw, dict) and isinstance(raw.get("data"), dict): raw = raw["data"]
                        if isinstance(raw, dict):
                            yield HarnessEvent(str(raw.get("type") or "unknown"), raw, event_id, raw.get("thread_id", raw.get("threadId")))
