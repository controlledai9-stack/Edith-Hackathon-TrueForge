"""Provider-neutral text model routing with quota-aware failover.

The public surface intentionally mirrors ``client.chat.completions.create`` so
existing Work Mode tool loops can use Groq first and Gemini second without
duplicating orchestration logic.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncGenerator

import requests
import httpx
from dotenv import set_key

import config

logger = logging.getLogger("EDITH")
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_OPENROUTER_FREE_FALLBACK = (
    ("nvidia/nemotron-3-ultra-550b-a55b:free", "NVIDIA Nemotron 3 Ultra"),
    ("poolside/laguna-s-2.1:free", "Poolside Laguna S 2.1"),
    ("nvidia/nemotron-3.5-lightning:free", "NVIDIA Nemotron 3.5 Lightning"),
    ("minimax/minimax-m3:free", "MiniMax M3"),
    ("nvidia/nemotron-3-super-120b-a12b:free", "NVIDIA Nemotron 3 Super"),
    ("cohere/north-mini-code:free", "Cohere North Mini Code"),
    ("dots-studio/dots-3-note-preview:free", "Dots3 Note Preview"),
    ("thinkingmachines/inkling:free", "Thinking Machines Inkling"),
    ("poolside/laguna-xs-2.1:free", "Poolside Laguna XS 2.1"),
    ("thinkingmachines/inkling-small:free", "Thinking Machines Inkling Small"),
)

_KNOWN_MODEL_NAMES = {
    "openai/gpt-oss-120b": "GPT-OSS 120B",
    "openai/gpt-oss-20b": "GPT-OSS 20B",
    "llama-3.3-70b-versatile": "Llama 3.3 70B",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "openrouter/free": "OpenRouter Free Models Router",
    "nvidia/nemotron-3-ultra-550b-a55b:free": "NVIDIA Nemotron 3 Ultra (free)",
    "nvidia/nemotron-3.5-lightning:free": "NVIDIA Nemotron 3.5 Lightning (free)",
    "nvidia/nemotron-3-super-120b-a12b:free": "NVIDIA Nemotron 3 Super (free)",
}


def model_display_name(model: str) -> str:
    value = str(model or "").strip()
    if value in _KNOWN_MODEL_NAMES:
        return _KNOWN_MODEL_NAMES[value]
    tail = value.rsplit("/", 1)[-1].removesuffix(":free")
    return re.sub(r"[-_]+", " ", tail).strip().title() or "Unknown model"


def _speed_hint(model: str) -> str:
    value = str(model or "").lower()
    if any(marker in value for marker in ("lightning", "flash", "20b", "mini", "nano", "xs")):
        return "fast"
    if any(marker in value for marker in ("ultra", "550b", "pro")):
        return "deep"
    return "balanced"


def _groq_keys() -> list[str]:
    keys = list(getattr(config, "GROQ_API_KEYS", []) or [])
    return [str(key).strip() for key in keys if str(key).strip()]


def _provider_order() -> list[str]:
    raw = str(getattr(config, "MODEL_PROVIDER_ORDER", "groq,gemini,openrouter") or "groq,gemini,openrouter")
    values = [item.strip().lower() for item in raw.split(",")]
    ordered = [item for item in values if item in {"groq", "gemini", "openrouter"}]
    for fallback in ("groq", "gemini", "openrouter"):
        if fallback not in ordered:
            ordered.append(fallback)
    return ordered


class _RoutedCompletions:
    def __init__(self, router: "ModelRouter", preference: str = "auto") -> None:
        self.router = router
        self.preference = preference

    def create(self, **kwargs: Any) -> Any:
        return self.router.create(preference=self.preference, **kwargs)


class RoutedChatClient:
    def __init__(self, router: "ModelRouter", preference: str = "auto") -> None:
        self.chat = SimpleNamespace(completions=_RoutedCompletions(router, preference))


class ModelRouter:
    def __init__(self) -> None:
        self._cooldowns: dict[str, float] = {}
        self._cooldown_kinds: dict[str, str] = {}
        self._last_provider = ""
        self._last_model = ""
        self._failovers = 0
        self._last_error = ""
        self._catalog_cache: tuple[float, list[dict[str, Any]]] = (0.0, [])

    @property
    def available(self) -> bool:
        return bool(
            _groq_keys()
            or str(getattr(config, "GEMINI_API_KEY", "")).strip()
            or str(getattr(config, "OPENROUTER_API_KEY", "")).strip()
        )

    def client(self, preference: str = "auto") -> RoutedChatClient:
        return RoutedChatClient(self, preference)

    @staticmethod
    def _is_quota_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return any(marker in text for marker in (
            "429", "rate limit", "rate_limit", "resource_exhausted", "quota", "tokens per day",
            "requests per day", "too many requests",
        ))

    def _cooldown(self, key: str, exc: Exception) -> None:
        # Daily quota responses should not be hammered; short burst limits can
        # be retried sooner. Either way the next configured provider runs now.
        text = str(exc).lower()
        seconds = 3600 if any(value in text for value in ("per day", "daily", "tokens per day")) else 75
        self._cooldowns[key] = time.time() + seconds
        self._cooldown_kinds[key] = "rate_limit"
        self._last_error = str(exc)[:300]

    def _candidates(self, preference: str = "auto") -> list[tuple[str, str, str, str | None]]:
        candidates: list[tuple[str, str, str, str | None]] = []
        selected = str(preference or "auto").strip()
        explicit_provider = ""
        explicit_model = ""
        if ":" in selected and selected != "auto":
            explicit_provider, explicit_model = selected.split(":", 1)
            explicit_provider = explicit_provider.lower()
            if not explicit_model or not re.fullmatch(r"[A-Za-z0-9._:/-]+", explicit_model):
                raise ValueError("The selected model identifier is invalid")
        providers = [explicit_provider] if explicit_provider in {"groq", "gemini", "openrouter"} else _provider_order()
        for provider in providers:
            if provider == "groq":
                candidates.extend(("groq", key, f"groq:{index + 1}{':' + explicit_model if explicit_model else ''}", explicit_model or None) for index, key in enumerate(_groq_keys()))
            elif provider == "gemini":
                key = str(getattr(config, "GEMINI_API_KEY", "") or "").strip()
                if key:
                    candidates.append(("gemini", key, f"gemini:1{':' + explicit_model if explicit_model else ''}", explicit_model or None))
            elif provider == "openrouter":
                key = str(getattr(config, "OPENROUTER_API_KEY", "") or "").strip()
                if key:
                    candidates.append(("openrouter", key, f"openrouter:1{':' + explicit_model if explicit_model else ''}", explicit_model or None))
        now = time.time()
        return [item for item in candidates if self._cooldowns.get(item[2], 0) <= now]

    def _cooldown_error(self) -> RuntimeError:
        now = time.time()
        active = [(key, until) for key, until in self._cooldowns.items() if until > now]
        waits = [max(1, int(until - now)) for _, until in active]
        wait = min(waits) if waits else 60
        if active and all(self._cooldown_kinds.get(key) == "rate_limit" for key, _ in active):
            return RuntimeError(
                f"All configured model providers are temporarily rate-limited. Try again in about {wait} seconds."
            )
        return RuntimeError(
            f"The configured model providers are temporarily unavailable after connection errors. "
            f"E.D.I.T.H. can try them again in about {wait} seconds."
        )

    @staticmethod
    def _provider_configured(provider: str) -> bool:
        if provider == "groq":
            return bool(_groq_keys())
        if provider == "gemini":
            return bool(str(getattr(config, "GEMINI_API_KEY", "") or "").strip())
        if provider == "openrouter":
            return bool(str(getattr(config, "OPENROUTER_API_KEY", "") or "").strip())
        return False

    def describe_selection(self, preference: str = "auto") -> dict[str, Any]:
        selected = str(preference or "auto").strip()
        if selected != "auto" and ":" in selected:
            provider, model = selected.split(":", 1)
            provider = provider.lower()
            return {
                "selection": "explicit",
                "provider": provider,
                "model": model,
                "label": model_display_name(model),
                "configured": self._provider_configured(provider),
                "speed": _speed_hint(model),
            }
        provider = self._last_provider or next((item for item in _provider_order() if self._provider_configured(item)), "")
        if self._last_model:
            model = self._last_model
        elif provider == "groq":
            model = str(getattr(config, "GROQ_MODEL", "openai/gpt-oss-120b"))
        elif provider == "gemini":
            model = str(getattr(config, "GEMINI_TEXT_MODEL", "gemini-2.5-flash"))
        elif provider == "openrouter":
            model = str(getattr(config, "OPENROUTER_MODEL", "openrouter/free"))
        else:
            model = ""
        return {
            "selection": "auto",
            "provider": provider or None,
            "model": model or None,
            "label": model_display_name(model) if model else "No model available",
            "configured": bool(provider),
            "speed": _speed_hint(model),
        }

    def create(self, *, preference: str = "auto", **kwargs: Any) -> Any:
        if not self.available and preference == "auto":
            raise RuntimeError("No text model provider is configured. Add a Groq, Gemini, or OpenRouter API key in Settings.")
        errors: list[str] = []
        candidates = self._candidates(preference)
        if not candidates:
            if preference != "auto":
                provider_id = str(preference).split(":", 1)[0].lower()
                if not self._provider_configured(provider_id):
                    raise RuntimeError(f"{provider_id.title()} is not configured. Add its API key in Settings or choose Auto.")
            raise self._cooldown_error()
        for index, (provider, key, identity, selected_model) in enumerate(candidates):
            try:
                provider_kwargs = dict(kwargs)
                if selected_model:
                    provider_kwargs["model"] = selected_model
                if provider == "groq":
                    from groq import Groq
                    result = Groq(api_key=key).chat.completions.create(**provider_kwargs)
                elif provider == "gemini":
                    result = self._gemini_create(key, provider_kwargs, selected_model)
                else:
                    result = self._openrouter_create(key, provider_kwargs, selected_model)
                if index:
                    self._failovers += 1
                self._last_provider = provider
                self._last_model = str(getattr(result, "model", "") or selected_model or provider_kwargs.get("model") or "")
                self._last_error = ""
                return result
            except Exception as exc:
                errors.append(f"{provider}: {exc}")
                logger.warning("[MODEL ROUTER] %s failed: %s", identity, exc)
                if self._is_quota_error(exc):
                    self._cooldown(identity, exc)
                else:
                    self._cooldowns[identity] = time.time() + 20
                    self._cooldown_kinds[identity] = "connection"
                    self._last_error = str(exc)[:300]
        raise RuntimeError("All configured model providers failed. " + " | ".join(errors[-3:]))

    def complete(
        self,
        system: str,
        user: str,
        *,
        model: str | None = None,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
        preference: str = "auto",
        max_tokens: int | None = None,
    ) -> str:
        options: dict[str, Any] = {
            "model": model or getattr(config, "GROQ_MODEL", "openai/gpt-oss-120b"),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
        }
        if response_format:
            options["response_format"] = response_format
        if max_tokens:
            options["max_tokens"] = int(max_tokens)
        response = self.create(preference=preference, **options)
        return str(response.choices[0].message.content or "").strip()

    async def astream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float,
        preference: str = "auto",
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        # Groq provides true streaming. Gemini's REST fallback is returned in
        # readable chunks so the UI continues to update progressively.
        candidates = self._candidates(preference)
        if not candidates:
            if preference != "auto":
                provider_id = str(preference).split(":", 1)[0].lower()
                if not self._provider_configured(provider_id):
                    raise RuntimeError(f"{provider_id.title()} is not configured. Add its API key in Settings or choose Auto.")
            raise self._cooldown_error()
        errors: list[str] = []
        for index, (provider, key, identity, selected_model) in enumerate(candidates):
            emitted = False
            try:
                if provider == "groq":
                    from groq import AsyncGroq
                    stream_options = {
                        "model": selected_model or model,
                        "messages": messages,
                        "temperature": temperature,
                        "stream": True,
                    }
                    if max_tokens:
                        stream_options["max_tokens"] = int(max_tokens)
                    stream = await AsyncGroq(api_key=key).chat.completions.create(**stream_options)
                    async for chunk in stream:
                        text = str(chunk.choices[0].delta.content or "")
                        if text:
                            emitted = True
                            yield text
                elif provider == "gemini":
                    response = await asyncio.to_thread(
                        self._gemini_create,
                        key,
                        {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                        selected_model,
                    )
                    text = str(response.choices[0].message.content or "")
                    for piece in re.findall(r".{1,180}(?:\s+|$)", text, flags=re.S):
                        emitted = True
                        yield piece
                        await asyncio.sleep(0)
                else:
                    async for piece in self._openrouter_astream(
                        key,
                        {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                        selected_model,
                    ):
                        emitted = True
                        yield piece
                if index:
                    self._failovers += 1
                self._last_provider = provider
                if provider != "openrouter" or selected_model or not self._last_model:
                    self._last_model = str(
                        selected_model
                        or (getattr(config, "GEMINI_TEXT_MODEL", "") if provider == "gemini" else model)
                        or ""
                    )
                self._last_error = ""
                return
            except Exception as exc:
                errors.append(f"{provider}: {exc}")
                logger.warning("[MODEL ROUTER] streaming %s failed: %s", identity, exc)
                if emitted:
                    raise
                if self._is_quota_error(exc):
                    self._cooldown(identity, exc)
                else:
                    self._cooldowns[identity] = time.time() + 20
                    self._cooldown_kinds[identity] = "connection"
                    self._last_error = str(exc)[:300]
        raise RuntimeError("All configured model providers failed. " + " | ".join(errors[-3:]))

    @staticmethod
    def _gemini_contents(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []
        call_names: dict[str, str] = {}
        for message in messages:
            role = str(message.get("role") or "user")
            content = message.get("content")
            if role == "system":
                if content:
                    system_parts.append(str(content))
                continue
            if role == "tool":
                name = call_names.get(str(message.get("tool_call_id") or ""), "tool")
                try:
                    response_data = json.loads(str(content or "{}"))
                except ValueError:
                    response_data = {"result": str(content or "")}
                contents.append({"role": "user", "parts": [{"functionResponse": {"name": name, "response": response_data}}]})
                continue
            parts: list[dict[str, Any]] = []
            if content:
                parts.append({"text": str(content)})
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                name = str(function.get("name") or "tool")
                call_names[str(call.get("id") or name)] = name
                try:
                    args = json.loads(str(function.get("arguments") or "{}"))
                except ValueError:
                    args = {}
                parts.append({"functionCall": {"name": name, "args": args}})
            if parts:
                contents.append({"role": "model" if role == "assistant" else "user", "parts": parts})
        return "\n\n".join(system_parts), contents

    def _gemini_create(self, key: str, kwargs: dict[str, Any], selected_model: str | None = None) -> Any:
        model = str(selected_model or getattr(config, "GEMINI_TEXT_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
            raise ValueError("GEMINI_TEXT_MODEL contains unsupported characters")
        system, contents = self._gemini_contents(list(kwargs.get("messages") or []))
        payload: dict[str, Any] = {"contents": contents or [{"role": "user", "parts": [{"text": "Continue."}]}]}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        generation = {"temperature": float(kwargs.get("temperature", 0.2))}
        if kwargs.get("max_tokens"):
            generation["maxOutputTokens"] = int(kwargs["max_tokens"])
        if (kwargs.get("response_format") or {}).get("type") == "json_object":
            generation["responseMimeType"] = "application/json"
        payload["generationConfig"] = generation
        tools = kwargs.get("tools") or []
        if tools:
            declarations = []
            for tool in tools:
                function = tool.get("function") or {}
                declarations.append({
                    "name": function.get("name"),
                    "description": function.get("description", ""),
                    "parameters": function.get("parameters") or {"type": "object", "properties": {}},
                })
            payload["tools"] = [{"functionDeclarations": declarations}]
        response = requests.post(
            f"{_GEMINI_BASE}/{model}:generateContent",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json=payload,
            timeout=(10, 45),
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:500]}")
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini returned no completion")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "\n".join(str(part.get("text")) for part in parts if part.get("text")).strip()
        calls = []
        for number, part in enumerate(parts):
            call = part.get("functionCall")
            if not call:
                continue
            calls.append(SimpleNamespace(
                id=f"gemini_call_{int(time.time() * 1000)}_{number}",
                type="function",
                function=SimpleNamespace(name=call.get("name"), arguments=json.dumps(call.get("args") or {})),
            ))
        message = SimpleNamespace(content=text, tool_calls=calls)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], model=model)

    @staticmethod
    def _openrouter_create(key: str, kwargs: dict[str, Any], selected_model: str | None = None) -> Any:
        model = str(selected_model or getattr(config, "OPENROUTER_MODEL", "openrouter/free") or "openrouter/free")
        payload = {
            field: value for field, value in kwargs.items()
            if value is not None and field in {"messages", "temperature", "max_tokens", "response_format", "tools", "tool_choice"}
        }
        payload["model"] = model
        response = requests.post(
            _OPENROUTER_CHAT_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "EDITH",
            },
            json=payload,
            timeout=(10, 60),
        )
        if response.status_code >= 400:
            raise RuntimeError(f"OpenRouter HTTP {response.status_code}: {response.text[:500]}")
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("OpenRouter returned no completion")
        raw_message = choices[0].get("message") or {}
        calls = []
        for number, call in enumerate(raw_message.get("tool_calls") or []):
            function = call.get("function") or {}
            calls.append(SimpleNamespace(
                id=str(call.get("id") or f"openrouter_call_{number}"),
                type="function",
                function=SimpleNamespace(
                    name=str(function.get("name") or "tool"),
                    arguments=str(function.get("arguments") or "{}"),
                ),
            ))
        message = SimpleNamespace(content=str(raw_message.get("content") or ""), tool_calls=calls)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], model=str(data.get("model") or model))

    async def _openrouter_astream(self, key: str, kwargs: dict[str, Any], selected_model: str | None = None) -> AsyncGenerator[str, None]:
        """Use OpenRouter's native SSE stream so text appears as tokens arrive."""
        model = str(selected_model or getattr(config, "OPENROUTER_MODEL", "openrouter/free") or "openrouter/free")
        payload = {
            field: value for field, value in kwargs.items()
            if value is not None and field in {"messages", "temperature", "max_tokens", "response_format", "tools", "tool_choice"}
        }
        payload.update({"model": model, "stream": True})
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "EDITH",
        }
        timeout = httpx.Timeout(60.0, connect=12.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", _OPENROUTER_CHAT_URL, headers=headers, json=payload) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    raise RuntimeError(f"OpenRouter HTTP {response.status_code}: {body[:500]}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        data = json.loads(raw)
                    except ValueError:
                        continue
                    if data.get("model"):
                        self._last_model = str(data["model"])
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    content = (choices[0].get("delta") or {}).get("content")
                    if isinstance(content, str) and content:
                        yield content

    def catalog(self) -> list[dict[str, Any]]:
        """Return configured direct models plus OpenRouter's current top free models."""
        now = time.time()
        if self._catalog_cache[1] and now - self._catalog_cache[0] < 900:
            return self._catalog_cache[1]
        entries: list[dict[str, Any]] = [
            {"value": "auto", "provider": "Auto", "name": "Auto · Groq → Gemini → OpenRouter", "configured": self.available, "speed": "fast"},
            {"value": "groq:openai/gpt-oss-20b", "provider": "Groq", "name": "GPT-OSS 20B", "configured": bool(_groq_keys()), "speed": "fast"},
            {"value": "groq:openai/gpt-oss-120b", "provider": "Groq", "name": "GPT-OSS 120B", "configured": bool(_groq_keys()), "speed": "balanced"},
            {"value": "groq:llama-3.3-70b-versatile", "provider": "Groq", "name": "Llama 3.3 70B", "configured": bool(_groq_keys()), "speed": "balanced"},
            {"value": "gemini:gemini-2.5-flash", "provider": "Gemini", "name": "Gemini 2.5 Flash", "configured": bool(str(getattr(config, "GEMINI_API_KEY", "")).strip()), "speed": "fast"},
            {"value": "gemini:gemini-2.5-pro", "provider": "Gemini", "name": "Gemini 2.5 Pro", "configured": bool(str(getattr(config, "GEMINI_API_KEY", "")).strip()), "speed": "deep"},
            {"value": "openrouter:openrouter/free", "provider": "OpenRouter", "name": "Free Models Router", "configured": bool(str(getattr(config, "OPENROUTER_API_KEY", "")).strip()), "speed": "variable"},
        ]
        try:
            response = requests.get(
                _OPENROUTER_MODELS_URL,
                params={"max_price": 0, "sort": "top-weekly", "limit": 10},
                timeout=12,
            )
            response.raise_for_status()
            configured = bool(str(getattr(config, "OPENROUTER_API_KEY", "")).strip())
            for item in (response.json().get("data") or [])[:10]:
                model_id = str(item.get("id") or "").strip()
                if model_id and model_id != "openrouter/free":
                    entries.append({
                        "value": f"openrouter:{model_id}",
                        "provider": "OpenRouter · Free",
                        "name": str(item.get("name") or model_id),
                        "configured": configured,
                        "speed": _speed_hint(model_id),
                    })
        except Exception as exc:
            logger.warning("[MODEL ROUTER] Could not refresh OpenRouter catalog: %s", exc)
            configured = bool(str(getattr(config, "OPENROUTER_API_KEY", "")).strip())
            entries.extend({
                "value": f"openrouter:{model_id}",
                "provider": "OpenRouter · Free",
                "name": name,
                "configured": configured,
                "speed": _speed_hint(model_id),
            } for model_id, name in _OPENROUTER_FREE_FALLBACK)
        self._catalog_cache = (now, entries)
        return entries

    def status(self) -> dict[str, Any]:
        now = time.time()
        return {
            "available": self.available,
            "provider_order": _provider_order(),
            "groq_keys": len(_groq_keys()),
            "gemini_configured": bool(str(getattr(config, "GEMINI_API_KEY", "")).strip()),
            "openrouter_configured": bool(str(getattr(config, "OPENROUTER_API_KEY", "")).strip()),
            "last_provider": self._last_provider or None,
            "last_model": self._last_model or None,
            "failovers": self._failovers,
            "cooldowns": {key: max(0, int(until - now)) for key, until in self._cooldowns.items() if until > now},
            "last_error": self._last_error or None,
        }


_router: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router


def reset_model_router() -> ModelRouter:
    global _router
    _router = ModelRouter()
    return _router


def save_model_settings(values: dict[str, Any], env_path: Path | None = None) -> dict[str, Any]:
    path = env_path or (config.BASE_DIR / ".env")
    order = str(values.get("provider_order") or "").strip().lower()
    if order:
        requested = [item.strip() for item in order.split(",") if item.strip() in {"groq", "gemini", "openrouter"}]
        normalized_order = ",".join(dict.fromkeys([*requested, "groq", "gemini", "openrouter"]))
        set_key(str(path), "MODEL_PROVIDER_ORDER", normalized_order, quote_mode="always")
        os.environ["MODEL_PROVIDER_ORDER"] = normalized_order
        config.MODEL_PROVIDER_ORDER = normalized_order
    raw_groq = values.get("groq_api_keys")
    if raw_groq is not None and str(raw_groq).strip():
        keys = [item.strip() for item in re.split(r"[\r\n,]+", str(raw_groq)) if item.strip()]
        if any(len(key) > 4096 for key in keys) or len(keys) > 12:
            raise ValueError("Provide at most 12 valid Groq API keys")
        for index, key in enumerate(keys, start=1):
            name = "GROQ_API_KEY" if index == 1 else f"GROQ_API_KEY_{index}"
            set_key(str(path), name, key, quote_mode="always")
            os.environ[name] = key
        config.GROQ_API_KEYS = keys
        config.GROQ_API_KEY = keys[0] if keys else ""
    gemini_key = str(values.get("gemini_api_key") or "").strip()
    if gemini_key:
        if len(gemini_key) > 4096 or "\n" in gemini_key:
            raise ValueError("Gemini API key is invalid")
        set_key(str(path), "GEMINI_API_KEY", gemini_key, quote_mode="always")
        os.environ["GEMINI_API_KEY"] = gemini_key
        config.GEMINI_API_KEY = gemini_key
    openrouter_key = str(values.get("openrouter_api_key") or "").strip()
    if openrouter_key:
        if len(openrouter_key) > 4096 or "\n" in openrouter_key:
            raise ValueError("OpenRouter API key is invalid")
        set_key(str(path), "OPENROUTER_API_KEY", openrouter_key, quote_mode="always")
        os.environ["OPENROUTER_API_KEY"] = openrouter_key
        config.OPENROUTER_API_KEY = openrouter_key
    for field, env_name in (("groq_model", "GROQ_MODEL"), ("gemini_model", "GEMINI_TEXT_MODEL"), ("openrouter_model", "OPENROUTER_MODEL")):
        value = str(values.get(field) or "").strip()
        if value:
            if not re.fullmatch(r"[A-Za-z0-9/._-]+", value):
                raise ValueError(f"{field.replace('_', ' ').title()} is invalid")
            set_key(str(path), env_name, value, quote_mode="always")
            os.environ[env_name] = value
            setattr(config, env_name, value)
    router = reset_model_router()
    return router.status()


def test_model_connections() -> dict[str, Any]:
    """Validate saved provider credentials without generating text or exposing keys."""
    providers: dict[str, dict[str, str]] = {}
    checks: list[tuple[str, str, dict[str, str], dict[str, Any] | None]] = []
    groq_keys = _groq_keys()
    if groq_keys:
        checks.append(("groq", "https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {groq_keys[0]}"}, None))
    gemini_key = str(getattr(config, "GEMINI_API_KEY", "") or "").strip()
    if gemini_key:
        checks.append(("gemini", _GEMINI_BASE, {"x-goog-api-key": gemini_key}, {"pageSize": 1}))
    openrouter_key = str(getattr(config, "OPENROUTER_API_KEY", "") or "").strip()
    if openrouter_key:
        checks.append(("openrouter", _OPENROUTER_MODELS_URL, {"Authorization": f"Bearer {openrouter_key}"}, {"limit": 1}))

    configured = {name for name, *_ in checks}
    for name in ("groq", "gemini", "openrouter"):
        if name not in configured:
            providers[name] = {"status": "not_configured", "message": "Not configured (optional)."}

    for name, url, headers, params in checks:
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code < 400:
                providers[name] = {"status": "connected", "message": "Connected — saved key is usable."}
            elif response.status_code in {401, 403}:
                providers[name] = {"status": "rejected", "message": f"Key rejected (HTTP {response.status_code}). Replace it in Global AI providers."}
            elif response.status_code == 429:
                providers[name] = {"status": "limited", "message": "Key is recognized, but this provider is currently rate-limited."}
            else:
                providers[name] = {"status": "error", "message": f"Provider returned HTTP {response.status_code}."}
        except requests.RequestException as exc:
            lowered = str(exc).lower()
            if "winerror 10013" in lowered or "forbidden by its access permissions" in lowered:
                message = "Windows blocked outbound HTTPS for E.D.I.T.H. Allow python.exe in Firewall/security software."
            else:
                message = "Could not reach this provider. Check internet, proxy, or firewall settings."
            providers[name] = {"status": "network_error", "message": message}
    return {"providers": providers}
