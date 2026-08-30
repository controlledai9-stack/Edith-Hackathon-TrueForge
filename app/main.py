import asyncio
import base64
import json
import logging
import re
import threading
import time
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from config import (
    GROQ_API_KEYS,
    TAVILY_API_KEY,
    TTS_VOICE,
    TTS_RATE,
    TTS_PITCH,
    TTS_VOLUME,
    ASSISTANT_NAME,
    TRUEFORGE_AUTO_BOOTSTRAP,
)
from app.models import ChatRequest, TTSRequest
from app.services.chat_service import get_chat_service
from app.services.groq_service import get_groq_service
from app.services.realtime_service import get_realtime_service
from app.services.vision_service import get_vision_service
from app.services.vector_store import get_memory_store
from app.services.brain_service import BrainService
from app.services.task_executor import build_actions_and_background
from app.services.task_manager import get_task_manager
from app.services.decision_types import INTENT_CONTENT
from app.services.web_reader_service import get_web_reader_service
from app.services.watchlist_service import get_watchlist_service, discover_source_url
from app.services.scraper_service import get_scraper_service
from app.services.intelligence_service import needs_live_data, answer_live_query, matching_entities, compare_entities, explain_change
from app.services.change_detection_service import format_scan_change_report
from app.services.research_service import get_research_service
from app.services.research_mode_service import get_research_mode_service
from app.services.work_mode_service import get_work_mode_service
from app.services.universal_browser_service import get_universal_browser_service
from app.services.trueforge_service import get_trueforge_service
from app.services.plugin_configuration_service import plugin_configuration_service
from app.services.model_router import get_model_router, save_model_settings
from app.mcp.server import edith_mcp
from app.plugins.google_workspace import create_authorization_url, finish_authorization
from app.plugins.linkedin import create_linkedin_authorization_url, finish_linkedin_authorization
from app.plugins.registry import get_plugin_registry, get_plugin_marketplace
from app.plugins.utils import ARTIFACTS_DIR, validate_public_url
from app.utils.key_rotation import build_rotators
from app.utils.speech import prepare_tts_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("J.A.R.V.I.S")

BASE_DIR = Path(__file__).parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
AUDIO_DIR = Path(__file__).parent / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
STARTER_STYLE_KEY = "|".join((TTS_VOICE, TTS_RATE, TTS_PITCH, TTS_VOLUME))
STARTER_STYLE_STAMP = AUDIO_DIR / ".starter_voice_style"

CAM_BYPASS_TOKEN = "TTCAMTOKENTT"

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    async def _maybe_bootstrap() -> None:
        if not TRUEFORGE_AUTO_BOOTSTRAP:
            return
        try:
            await get_trueforge_service().bootstrap()
            logger.info("[TRUEFORGE] Connector and agent profiles bootstrapped")
        except Exception as exc:
            logger.warning("[TRUEFORGE] Automatic bootstrap skipped: %s", exc)

    if edith_mcp is not None:
        async with edith_mcp.session_manager.run():
            await _maybe_bootstrap()
            yield
    else:
        await _maybe_bootstrap()
        yield


app = FastAPI(title="E.D.I.T.H.", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Mcp-Session-Id"],
)

chat_service = get_chat_service()
groq_service = get_groq_service()
realtime_service = get_realtime_service()
vision_service = get_vision_service()
memory_store = get_memory_store()
task_manager = get_task_manager()
brain = BrainService()
web_reader = get_web_reader_service()
watchlist_service = get_watchlist_service()
scraper_service = get_scraper_service()
research_service = get_research_service()
research_mode_service = get_research_mode_service()
work_mode_service = get_work_mode_service()
universal_browser_service = get_universal_browser_service()
plugin_registry = get_plugin_registry()
plugin_marketplace = get_plugin_marketplace()
trueforge_service = get_trueforge_service()
rotators = build_rotators(GROQ_API_KEYS)
_active_chat_streams: dict[str, asyncio.Task] = {}
_active_chat_cancel_events: dict[str, threading.Event] = {}


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _split_sentences(text: str):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


async def _tts_bytes_b64(text: str) -> Optional[str]:
    text = prepare_tts_text(text)
    if not text:
        return None
    try:
        import edge_tts
        communicate = edge_tts.Communicate(
            text,
            TTS_VOICE,
            rate=TTS_RATE,
            pitch=TTS_PITCH,
            volume=TTS_VOLUME,
        )
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        if not audio_bytes:
            return None
        return base64.b64encode(audio_bytes).decode("ascii")
    except Exception as e:
        logger.warning("[TTS] Synthesis failed: %s", e)
        return None


@app.get("/health")
async def health():
    router_status = get_model_router().status()
    status = "healthy" if router_status["available"] else "degraded"
    return JSONResponse({
        "status": status,
        "groq": bool(GROQ_API_KEYS),
        "gemini": router_status["gemini_configured"],
        "openrouter": router_status["openrouter_configured"],
        "tavily": bool(TAVILY_API_KEY),
        "vector_store": memory_store.available,
        "trueforge_enabled": trueforge_service.enabled,
        "mcp_available": edith_mcp is not None,
    })


@app.get("/settings/models")
async def get_model_settings():
    import config as runtime_config
    status = get_model_router().status()
    return JSONResponse({
        **status,
        "groq_model": runtime_config.GROQ_MODEL,
        "gemini_model": runtime_config.GEMINI_TEXT_MODEL,
        "openrouter_model": runtime_config.OPENROUTER_MODEL,
        "links": {
            "groq": "https://console.groq.com/keys",
            "gemini": "https://aistudio.google.com/app/apikey",
            "openrouter": "https://openrouter.ai/settings/keys",
            "catalog": "https://openrouter.ai/models?max_price=0",
            "opencode": "https://opencode.ai/docs/providers",
        },
    })


@app.get("/settings/models/catalog")
async def get_model_catalog():
    return JSONResponse({"models": get_model_router().catalog()})


@app.post("/settings/models")
async def update_model_settings(payload: dict):
    try:
        status = save_model_settings(payload)
        return JSONResponse({"saved": True, **status})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/settings/models/test")
async def test_saved_model_connections():
    from app.services.model_router import test_model_connections
    return JSONResponse(await asyncio.to_thread(test_model_connections))


@app.get("/trueforge/status")
async def trueforge_status(refresh: bool = False):
    status = await trueforge_service.health(refresh=refresh)
    status["mcp_available"] = edith_mcp is not None
    if status.get("ok") and edith_mcp is None:
        status["ok"] = False
        status["error"] = (
            "E.D.I.T.H.'s MCP connector is unavailable. Start the app with the "
            "configured Python environment before using TrueForge tools."
        )
    return JSONResponse(status)


@app.post("/trueforge/bootstrap")
async def trueforge_bootstrap():
    try:
        return JSONResponse(await trueforge_service.bootstrap())
    except Exception as exc:
        logger.exception("[TRUEFORGE] Bootstrap failed")
        raise HTTPException(status_code=503, detail=str(exc))


def _profile(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"general", "research", "code", "work"}:
        raise HTTPException(status_code=422, detail="Unknown TrueForge profile")
    return normalized


@app.post("/trueforge/sessions/{session_id}/cancel")
async def cancel_trueforge_turn(session_id: str, payload: dict):
    try:
        result = await trueforge_service.cancel(session_id, _profile(str(payload.get("profile") or "general")))
        return JSONResponse({"cancelled": True, "data": result})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


async def _approval_stream(session_id: str, payload: dict) -> AsyncGenerator[str, None]:
    profile = _profile(str(payload.get("profile") or "general"))
    try:
        async for item in trueforge_service.approve(
            session_id,
            profile,
            str(payload.get("tool_call_id") or ""),
            str(payload.get("thread_id") or "main"),
            bool(payload.get("allow")),
            str(payload.get("reason") or ""),
        ):
            yield _sse(item)
    except Exception as exc:
        error_text = str(exc)
        if "429" in error_text or "rate limit" in error_text.lower():
            yield _sse({"auto_resume": {"reason": "rate_limit", "after_seconds": 60, "profile": profile}})
        else:
            yield _sse({"error": error_text})
    yield _sse({"done": True})


async def _harness_continuation_stream(generator, profile: str = "general") -> AsyncGenerator[str, None]:
    try:
        async for item in generator:
            yield _sse(item)
    except Exception as exc:
        logger.exception("[TRUEFORGE] Continuation failed")
        error_text = str(exc)
        if "429" in error_text or "rate limit" in error_text.lower():
            yield _sse({"auto_resume": {"reason": "rate_limit", "after_seconds": 60, "profile": profile}})
        else:
            yield _sse({"error": error_text})
    yield _sse({"done": True})


@app.post("/trueforge/sessions/{session_id}/approval")
async def approve_trueforge_tool(session_id: str, payload: dict):
    if not payload.get("tool_call_id"):
        raise HTTPException(status_code=422, detail="tool_call_id is required")
    return StreamingResponse(_approval_stream(session_id, payload), media_type="text/event-stream")


@app.post("/trueforge/sessions/{session_id}/response")
async def respond_to_trueforge_question(session_id: str, payload: dict):
    if not payload.get("tool_call_id") or not str(payload.get("content") or "").strip():
        raise HTTPException(status_code=422, detail="tool_call_id and content are required")
    profile = _profile(str(payload.get("profile") or "general"))
    generator = trueforge_service.respond(
        session_id,
        profile,
        str(payload["tool_call_id"]),
        str(payload.get("thread_id") or "main"),
        str(payload["content"]).strip(),
    )
    return StreamingResponse(_harness_continuation_stream(generator, profile), media_type="text/event-stream")


@app.post("/trueforge/sessions/{session_id}/resume-auth")
async def resume_trueforge_after_auth(session_id: str, payload: dict):
    profile = _profile(str(payload.get("profile") or "general"))
    generator = trueforge_service.resume_auth(
        session_id, profile
    )
    return StreamingResponse(_harness_continuation_stream(generator, profile), media_type="text/event-stream")


@app.post("/trueforge/sessions/{session_id}/resume")
async def resume_trueforge_turn(session_id: str, payload: dict):
    profile = _profile(str(payload.get("profile") or "general"))
    generator = trueforge_service.resume(
        session_id, profile
    )
    return StreamingResponse(_harness_continuation_stream(generator, profile), media_type="text/event-stream")


@app.post("/trueforge/sessions/{session_id}/retry-rate-limit")
async def retry_rate_limited_trueforge_turn(session_id: str, payload: dict):
    profile = _profile(str(payload.get("profile") or "general"))
    generator = trueforge_service.retry_rate_limited(
        session_id, profile
    )
    return StreamingResponse(_harness_continuation_stream(generator, profile), media_type="text/event-stream")


@app.post("/tts")
async def tts_endpoint(req: TTSRequest):
    audio_b64 = await _tts_bytes_b64(req.text)
    if not audio_b64:
        raise HTTPException(status_code=503, detail="TTS synthesis failed")
    return JSONResponse({"audio": audio_b64})


@app.get("/tts/starter/{index}")
async def tts_starter(index: int):
    """Serve filler audio only when it matches the active reply voice profile."""
    if index < 1 or index > 10:
        raise HTTPException(status_code=404, detail="Unknown starter clip")
    cached_style = (
        STARTER_STYLE_STAMP.read_text(encoding="utf-8").strip()
        if STARTER_STYLE_STAMP.exists()
        else ""
    )
    clip = AUDIO_DIR / f"starter_{index}.mp3"
    if cached_style != STARTER_STYLE_KEY or not clip.exists():
        raise HTTPException(status_code=404, detail="Starter voice cache is not ready")
    return FileResponse(
        clip,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    task = task_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return JSONResponse(task)


@app.get("/browser/jobs/{job_id}")
async def get_browser_job(job_id: str):
    job = universal_browser_service.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Browser job not found")
    public = {key: value for key, value in job.items() if key not in {"task", "interactive_command"}}
    return JSONResponse(public)


@app.get("/browser/jobs/{job_id}/screenshot")
async def get_browser_job_screenshot(job_id: str):
    if not universal_browser_service.get(job_id):
        raise HTTPException(status_code=404, detail="Browser job not found")
    screenshot = universal_browser_service.screenshot_path(job_id)
    if not screenshot.is_file():
        raise HTTPException(status_code=404, detail="Browser preview is not ready")
    return FileResponse(screenshot, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.post("/browser/jobs/{job_id}/cancel")
async def cancel_browser_job(job_id: str):
    job = universal_browser_service.cancel(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Browser job not found")
    public = {key: value for key, value in job.items() if key not in {"task", "interactive_command"}}
    return JSONResponse(public)


@app.post("/browser/jobs/{job_id}/interact")
async def interact_with_browser_job(job_id: str, command: dict):
    try:
        job = universal_browser_service.interact(job_id, command)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not job:
        raise HTTPException(status_code=404, detail="Browser job not found")
    interaction_id = str((job.get("interactive_command") or {}).get("id") or "")
    public = {key: value for key, value in job.items() if key not in {"task", "interactive_command"}}
    public["interaction_id"] = interaction_id
    return JSONResponse(public)


@app.get("/chat/sessions")
async def list_chat_sessions():
    sessions = chat_service.list_sessions()
    return JSONResponse({"sessions": sessions})


@app.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str):
    removed = chat_service.delete_session(session_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Session not found")
    return JSONResponse({"deleted": True, "session_id": session_id})


@app.post("/chat/sessions/{session_id}/cancel-turn")
async def cancel_chat_turn(session_id: str, payload: dict):
    """Cancel the live response task and, when present, its TrueForge turn."""
    cancel_event = _active_chat_cancel_events.get(session_id)
    if cancel_event is not None:
        cancel_event.set()
    stream_task = _active_chat_streams.get(session_id)
    stream_cancelled = bool(stream_task and not stream_task.done())
    if stream_cancelled:
        stream_task.cancel()
    harness_cancelled = False
    try:
        await trueforge_service.cancel(session_id, _profile(str(payload.get("profile") or "general")))
        harness_cancelled = True
    except Exception:
        # Most General/Research turns never create a TrueForge session.
        pass
    return JSONResponse({
        "cancelled": stream_cancelled or harness_cancelled,
        "stream_cancelled": stream_cancelled,
        "harness_cancelled": harness_cancelled,
    })


@app.get("/chat/history/{session_id}")
async def get_history(session_id: str):
    history = chat_service.get_history(session_id)
    return JSONResponse({
        "session_id": session_id,
        "turns": [{"user": u, "assistant": a} for u, a in history],
    })


@app.get("/chat/context/{session_id}/stats")
async def get_context_stats(session_id: str):
    """Expose local compaction metrics without returning prompt contents."""
    return JSONResponse(chat_service.get_context_stats(session_id))


@app.get("/plugins")
async def list_plugins():
    return JSONResponse({"plugins": plugin_configuration_service.decorate(plugin_registry.list_plugins())})


@app.get("/plugins/{plugin_id}/configuration")
async def get_plugin_configuration(plugin_id: str):
    try:
        return JSONResponse(plugin_configuration_service.schema(plugin_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="This plugin does not have local configuration fields")


@app.post("/plugins/{plugin_id}/configuration")
async def save_plugin_configuration(plugin_id: str, payload: dict):
    try:
        result = plugin_configuration_service.save(plugin_id, payload.get("values") or {})
        result["plugin"] = plugin_configuration_service.decorate([plugin_registry.get_plugin(plugin_id).metadata()])[0] if plugin_registry.get_plugin(plugin_id) else None
        return JSONResponse(result)
    except KeyError:
        raise HTTPException(status_code=404, detail="This plugin does not have local configuration fields")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/plugins/store")
async def list_plugin_store():
    return JSONResponse({"plugins": plugin_marketplace.catalog()})


@app.post("/plugins/store/{plugin_id}/install")
async def install_store_plugin(plugin_id: str):
    try:
        return JSONResponse(plugin_marketplace.install(plugin_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="Store plugin not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/plugins/store/install-manifest")
async def install_plugin_manifest(payload: dict):
    manifest_url = str(payload.get("url") or "").strip()
    if not manifest_url.startswith("https://"):
        raise HTTPException(status_code=422, detail="Plugin manifests must use HTTPS")
    try:
        import requests
        validate_public_url(manifest_url)
        response = requests.get(manifest_url, timeout=15, allow_redirects=False, headers={"Accept": "application/json"})
        response.raise_for_status()
        if len(response.content) > 1_000_000:
            raise ValueError("Plugin manifest is too large")
        manifest = response.json()
        if not isinstance(manifest, dict):
            raise ValueError("Plugin manifest must be a JSON object")
        validate_public_url(str(manifest.get("homepage") or ""))
        return JSONResponse(plugin_marketplace.install_manifest(manifest))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Could not download plugin manifest: {exc}")


@app.get("/artifacts/{filename}")
async def download_artifact(filename: str):
    safe_name = Path(filename).name
    path = (ARTIFACTS_DIR / safe_name).resolve()
    if ARTIFACTS_DIR.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path, filename=safe_name)


@app.get("/artifacts/{filename}/preview")
async def preview_artifact(filename: str):
    safe_name = Path(filename).name
    path = (ARTIFACTS_DIR / safe_name).resolve()
    if ARTIFACTS_DIR.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path, headers={"Cache-Control": "private, no-store"})


@app.get("/research-mode/files")
async def list_research_mode_files():
    return JSONResponse({"files": research_mode_service.list_files()})


@app.get("/research-mode/sessions/{session_id}/sources")
async def list_research_sources(session_id: str):
    sources = research_mode_service.list_sources(session_id)
    return JSONResponse({
        "session_id": session_id,
        "sources": sources,
        "enabled_tokens": sum(item["token_count"] for item in sources if item["enabled"]),
    })


@app.patch("/research-mode/sessions/{session_id}/sources/{source_id}")
async def update_research_source(session_id: str, source_id: str, payload: dict):
    if "enabled" not in payload:
        raise HTTPException(status_code=422, detail="The enabled field is required")
    try:
        return JSONResponse(research_mode_service.set_source_enabled(session_id, source_id, bool(payload["enabled"])))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Research source not found")


@app.delete("/research-mode/sessions/{session_id}/sources/{source_id}")
async def delete_research_source(session_id: str, source_id: str):
    if not research_mode_service.delete_source(session_id, source_id):
        raise HTTPException(status_code=404, detail="Research source not found")
    return JSONResponse({"deleted": True, "source_id": source_id})


def _research_file_path(category: str, filename: str) -> Path:
    roots = {
        "solutions": research_mode_service.files_dir,
        "snaps": research_mode_service.images_dir,
    }
    root = roots.get(category)
    if root is None:
        raise HTTPException(status_code=404, detail="Research file category not found")
    safe_name = Path(filename).name
    path = (root / safe_name).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Research file not found")
    return path


@app.get("/research-mode/files/{category}/{filename}/content")
async def read_research_mode_file(category: str, filename: str):
    if category != "solutions":
        raise HTTPException(status_code=400, detail="Only solution documents can be edited")
    path = _research_file_path(category, filename)
    return JSONResponse({"name": path.name, "content": path.read_text(encoding="utf-8")})


@app.put("/research-mode/files/{category}/{filename}/content")
async def save_research_mode_file(category: str, filename: str, payload: dict):
    if category != "solutions":
        raise HTTPException(status_code=400, detail="Only solution documents can be edited")
    path = _research_file_path(category, filename)
    content = payload.get("content")
    if not isinstance(content, str):
        raise HTTPException(status_code=422, detail="File content must be text")
    if len(content.encode("utf-8")) > 2_000_000:
        raise HTTPException(status_code=413, detail="Research file is too large to save")
    path.write_text(content, encoding="utf-8")
    return JSONResponse({"saved": True, "name": path.name, "size": path.stat().st_size})


@app.get("/research-mode/files/{category}/{filename}")
async def download_research_mode_file(category: str, filename: str):
    path = _research_file_path(category, filename)
    return FileResponse(path, filename=path.name)


@app.patch("/plugins/{plugin_id}")
async def update_plugin(plugin_id: str, payload: dict):
    try:
        return JSONResponse(plugin_registry.enable(plugin_id, bool(payload.get("enabled", True))))
    except KeyError:
        raise HTTPException(status_code=404, detail="Plugin not found")


@app.post("/plugins/{plugin_id}/disconnect")
async def disconnect_plugin(plugin_id: str):
    try:
        return JSONResponse(plugin_registry.disconnect(plugin_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="Plugin not found")


@app.get("/oauth/google/start")
async def google_oauth_start():
    try:
        return RedirectResponse(create_authorization_url())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/oauth/google/callback")
async def google_oauth_callback(state: str, code: str):
    try:
        finish_authorization(state, code)
        return HTMLResponse("<h2>Google connected to E.D.I.T.H.</h2><p>Gmail, Drive, Calendar, and Tasks are ready. You can close this window.</p><script>if(window.opener){window.opener.postMessage({type:'edith-google-connected'},window.location.origin)}setTimeout(()=>window.close(),1200)</script>")
    except Exception as exc:
        detail = str(exc)
        if "WinError 10013" in detail or "forbidden by its access permissions" in detail:
            detail = (
                "Google approved the sign-in, but Windows blocked EDITH from connecting to "
                "oauth2.googleapis.com:443 for the token exchange. Start EDITH from your normal "
                "local terminal or allow python.exe outbound HTTPS access, then connect Google again."
            )
        raise HTTPException(status_code=400, detail=detail)


@app.get("/oauth/linkedin/start")
async def linkedin_oauth_start():
    try:
        return RedirectResponse(create_linkedin_authorization_url())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/oauth/linkedin/callback")
async def linkedin_oauth_callback(state: str, code: str):
    try:
        finish_linkedin_authorization(state, code)
        return HTMLResponse("<h2>LinkedIn connected to E.D.I.T.H.</h2><p>You can close this window.</p><script>setTimeout(()=>window.close(),1200)</script>")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Watchlists (Feature 1 / 4)
# ---------------------------------------------------------------------------

@app.get("/watchlists")
async def list_watchlists():
    return JSONResponse({"watchlists": watchlist_service.get_watchlists()})


@app.post("/watchlists")
async def create_watchlist(payload: dict):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    categories = payload.get("categories") or None
    entity_type = payload.get("type", "company")
    entry = watchlist_service.add_watchlist(name, categories, entity_type)
    return JSONResponse(entry)


@app.delete("/watchlists/{name_or_id}")
async def delete_watchlist(name_or_id: str, category: Optional[str] = None):
    removed = watchlist_service.remove_watchlist(name_or_id, category)
    if not removed:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    return JSONResponse({"deleted": True})


@app.post("/watchlists/{name_or_id}/scan")
async def scan_watchlist(name_or_id: str):
    result = await asyncio.to_thread(watchlist_service.run_watchlist_scan, name_or_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return JSONResponse(result)


@app.post("/watchlists/scan-all")
async def scan_all_watchlists():
    results = await asyncio.to_thread(watchlist_service.run_all_watchlists)
    return JSONResponse({"results": results})


@app.get("/watchlists/{name_or_id}/history")
async def get_watchlist_history(name_or_id: str):
    result = watchlist_service.get_watchlist_history(name_or_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# Scraper Health dashboard (Feature 2)
# ---------------------------------------------------------------------------

@app.get("/scraper-health")
async def get_scraper_health():
    return JSONResponse({"sources": scraper_service.get_health_board()})


# ---------------------------------------------------------------------------
# Live Intelligence feed + monitoring history
# ---------------------------------------------------------------------------

@app.get("/intelligence/feed")
async def get_intelligence_feed(limit: int = 30):
    return JSONResponse({"changes": watchlist_service.get_recent_changes(limit)})


@app.get("/intelligence/history")
async def get_monitoring_history(limit: int = 50):
    return JSONResponse({"events": watchlist_service.get_history(limit)})


@app.get("/intelligence/summary")
async def get_intelligence_summary():
    """Aggregate dashboard metrics: monitored entities, active sources,
    scraper run success/failure counts, changes found, missions completed,
    and the most recent scan time across all watchlist entries."""
    watchlists = watchlist_service.get_watchlists()
    health_board = scraper_service.get_health_board()
    missions = research_service.list_missions(limit=500)
    changes = watchlist_service.get_recent_changes(limit=1000)

    success_states = {"HEALTHY", "RECOVERED"}
    failure_states = {"EXTRACTION_FAILED"}

    last_scans = [w["last_scan"] for w in watchlists if w.get("last_scan")]

    return JSONResponse({
        "monitored_entities": len(watchlists),
        "active_sources": sum(len(w.get("sources", [])) for w in watchlists),
        "runs_success": sum(1 for h in health_board if h.get("state") in success_states),
        "runs_failed": sum(1 for h in health_board if h.get("state") in failure_states),
        "changes_detected": len(changes),
        "missions_completed": sum(1 for m in missions if m.get("status") == "completed"),
        "last_scan": max(last_scans) if last_scans else None,
    })


@app.get("/intelligence/history/unified")
async def get_unified_history(limit: int = 60):
    """Merges monitoring events, scraper run history, detected changes, and
    research mission activity into one chronological timeline for the
    dashboard's History tab."""
    events: List[dict] = []

    for e in watchlist_service.get_history(limit=200):
        events.append({
            "type": e.get("type", "event"),
            "timestamp": e.get("timestamp"),
            "summary": f"{e.get('entity', '')}".strip() or e.get("type", "event"),
            "detail": e,
        })

    for source in scraper_service.get_health_board():
        for h in source.get("history", []):
            events.append({
                "type": "scraper_run",
                "timestamp": h.get("timestamp"),
                "summary": f"{source.get('entity')} / {source.get('category')} — {h.get('state')}",
                "detail": h,
            })

    for c in watchlist_service.get_recent_changes(limit=200):
        events.append({
            "type": "change",
            "timestamp": c.get("detected_at"),
            "summary": f"{c.get('entity')}: {c.get('change_type')} on {c.get('field')}",
            "detail": c,
        })

    for m in research_service.list_missions(limit=100):
        if m.get("started_at"):
            events.append({
                "type": "mission_started", "timestamp": m.get("started_at"),
                "summary": f"Research mission started: {m.get('query')}", "detail": {"mission_id": m.get("mission_id")},
            })
        if m.get("completed_at"):
            events.append({
                "type": "mission_completed", "timestamp": m.get("completed_at"),
                "summary": f"Research mission {m.get('status')}: {m.get('query')}", "detail": {"mission_id": m.get("mission_id")},
            })

    events = [e for e in events if e.get("timestamp")]
    events.sort(key=lambda e: e["timestamp"], reverse=True)
    return JSONResponse({"events": events[:limit]})


@app.post("/intelligence/explain-change")
async def explain_change_endpoint(payload: dict):
    explanation = await asyncio.to_thread(explain_change, payload)
    return JSONResponse({"explanation": explanation})


# ---------------------------------------------------------------------------
# Research Missions (Feature 5)
# ---------------------------------------------------------------------------

@app.post("/research/missions")
async def create_research_mission(payload: dict):
    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    mission = await asyncio.to_thread(research_service.start_mission, query)
    return JSONResponse(mission)


@app.get("/research/missions")
async def list_research_missions():
    return JSONResponse({"missions": research_service.list_missions()})


@app.get("/research/missions/{mission_id}")
async def get_research_mission(mission_id: str):
    mission = research_service.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return JSONResponse(mission)


_CATEGORY_KEYWORDS = [
    "products", "pricing", "new releases", "blog", "documentation",
    "api", "changelog", "features", "availability", "news", "models",
    "ai announcements", "announcements",
]

_SHOPPING_SITES = {
    "amazon": ("amazon.in", "https://www.amazon.in/s?k="),
    "flipkart": ("flipkart.com", "https://www.flipkart.com/search?q="),
    "ebay": ("ebay.com", "https://www.ebay.com/sch/i.html?_nkw="),
    "etsy": ("etsy.com", "https://www.etsy.com/search?q="),
    "walmart": ("walmart.com", "https://www.walmart.com/search?q="),
    "best buy": ("bestbuy.com", "https://www.bestbuy.com/site/searchpage.jsp?st="),
    "target": ("target.com", "https://www.target.com/s?searchTerm="),
    "ikea": ("ikea.com", "https://www.ikea.com/in/en/search/?q="),
    "aliexpress": ("aliexpress.com", "https://www.aliexpress.com/wholesale?SearchText="),
    "myntra": ("myntra.com", "https://www.myntra.com/"),
}

_BUDGET_PATTERN = re.compile(
    r"(?:\b(?:under|below|less\s+than|up\s+to|max(?:imum)?|budget(?:\s+of)?|within)\s*)"
    r"(?:(₹|\$|€|£|¥|rs\.?|inr|usd|eur|gbp)\s*)?"
    r"([0-9][0-9,]*(?:\.[0-9]+)?)"
    r"(?:\s*(rupees?|inr|dollars?|usd|euros?|eur|pounds?|gbp|yen|jpy))?\b",
    re.I,
)


def _extract_budget(text: str, site: str) -> dict | None:
    match = _BUDGET_PATTERN.search(text)
    if not match:
        return None
    amount = float(match.group(2).replace(",", ""))
    token = (match.group(1) or match.group(3) or "").lower().rstrip(".")
    currency = {
        "₹": "INR", "rs": "INR", "inr": "INR", "rupee": "INR", "rupees": "INR",
        "$": "USD", "usd": "USD", "dollar": "USD", "dollars": "USD",
        "€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR",
        "£": "GBP", "gbp": "GBP", "pound": "GBP", "pounds": "GBP",
        "¥": "JPY", "jpy": "JPY", "yen": "JPY",
    }.get(token, "INR" if site in ("amazon", "flipkart", "myntra") else "USD")
    symbols = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}
    return {
        "amount": amount, "currency": currency, "symbol": symbols[currency],
        "label": f"{symbols[currency]}{amount:g}", "matched_text": match.group(0),
    }


def _shopping_site_target(site: str, budget: dict | None) -> tuple[str, str]:
    if site == "amazon" and budget:
        return {
            "USD": ("amazon.com", "https://www.amazon.com/s?k="),
            "EUR": ("amazon.de", "https://www.amazon.de/s?k="),
            "GBP": ("amazon.co.uk", "https://www.amazon.co.uk/s?k="),
            "JPY": ("amazon.co.jp", "https://www.amazon.co.jp/s?k="),
        }.get(budget["currency"], _SHOPPING_SITES[site])
    return _SHOPPING_SITES[site]


def _clean_product_phrase(text: str) -> str:
    """Remove conversational shopping/review wording while keeping the product."""
    product = text.strip(" ,.!?")
    product = re.sub(
        r"^(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
        r"(?:find|show|search\s+for|look\s+up|recommend|suggest|shop\s+for|buy|give)\s+(?:me\s+)?",
        "", product, flags=re.I,
    )
    product = re.sub(r"^(?:a|an|some|the\s+best|best|top|good|highly[\s-]rated)\s+", "", product, flags=re.I)
    # Everything after these clauses is selection criteria, not part of the
    # product name (for example: "cat treats but only ... high ratings").
    if re.search(r"\b(?:ratings?|reviews?)\b", product, re.I):
        product = re.split(r"\s+(?:but|which|that|with)\b", product, maxsplit=1, flags=re.I)[0]
    product = re.split(
        r"\s*(?:,|\s+but\s+|\s+with\s+|\s+that\s+have\s+|\s+which\s+have\s+)"
        r"(?=(?:only\s+)?(?:really\s+)?(?:a\s+)?high\s+(?:number|volume)\s+of\s+(?:ratings|reviews))",
        product, maxsplit=1, flags=re.I,
    )[0]
    product = re.sub(
        r"\s+(?:with\s+)?(?:the\s+)?(?:highest|most|many|a\s+high\s+number\s+of)"
        r"\s+(?:customer\s+)?(?:ratings|reviews)\s*$",
        "", product, flags=re.I,
    )
    return product.strip(" ,.!?") or "products"


def _match_shopping_request(raw_msg: str, history=None):
    """Normalize explicit searches, recommendations, and contextual link follow-ups."""
    msg = _strip_wake_prefix(raw_msg).strip()
    site_pattern = "|".join(re.escape(site) for site in _SHOPPING_SITES)
    match = re.search(rf"\b(?:from|on|at)\s+({site_pattern})\b", msg, re.I)
    is_link_followup = bool(re.search(
        r"\b(?:direct\s+)?links?\b.*\b(?:them|those|these|their|products?)\b|"
        r"\b(?:them|those|these|their)\b.*\b(?:direct\s+)?links?\b|"
        r"^(?:give|send|show)\s+me\s+(?:the\s+)?(?:direct\s+)?links?\b",
        msg, re.I,
    ))
    if is_link_followup:
        for previous_user, _ in reversed(history or []):
            previous = _match_shopping_request(previous_user, None)
            if previous and not previous.get("followup"):
                previous["followup"] = True
                return previous
        return None

    shopping_verb = re.search(
        r"\b(?:find|show|search|look\s+up|recommend|suggest|shop|buy)\b", msg, re.I
    )
    recommendation = re.search(
        r"\b(?:recommend|suggest|best|top|most\s+reviewed|highest\s+number\s+of\s+(?:ratings|reviews))\b",
        msg, re.I,
    )
    if not shopping_verb and not recommendation:
        return None

    site = match.group(1).lower() if match else "amazon"
    budget = _extract_budget(msg, site)
    product_text = msg[:match.start()] if match else msg
    if budget:
        product_text = product_text.replace(budget["matched_text"], " ")
    product = _clean_product_phrase(product_text)
    prioritize_reviews = bool(re.search(
        r"\b(?:ratings?|reviews?|most\s+reviewed|high\s+(?:number|volume))\b", msg, re.I
    )) or bool(recommendation)
    return {
        "site": site,
        "product": product,
        "prioritize_reviews": prioritize_reviews,
        "budget": budget,
        "followup": False,
    }


def _extract_review_count(result: dict) -> int:
    """Extract only explicit rating/review counts; never infer or invent one."""
    text = " ".join(str(result.get(key) or "") for key in ("title", "content"))
    values = []
    patterns = (
        r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*([kKmM]?)\s+(?:global\s+)?(?:ratings?|reviews?)\b",
        r"(?:ratings?|reviews?)\s*[:(]?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([kKmM]?)\b",
    )
    for pattern in patterns:
        for number, suffix in re.findall(pattern, text, re.I):
            try:
                value = float(number.replace(",", ""))
                if suffix.lower() == "k": value *= 1_000
                elif suffix.lower() == "m": value *= 1_000_000
                values.append(int(value))
            except ValueError:
                continue
    return max(values, default=0)


def _extract_price(result: dict, currency: str) -> float:
    """Return an explicitly labelled product price, or zero when unavailable."""
    text = " ".join(str(result.get(key) or "") for key in ("title", "content"))
    currency_pattern = {
        "INR": r"(?:₹|Rs\.?|INR)", "USD": r"(?:US\s*)?\$", "EUR": r"€",
        "GBP": r"£", "JPY": r"¥",
    }.get(currency, r"(?:₹|\$|€|£|¥)")
    patterns = (
        rf"(?:product\s+summary|price|deal\s+price|offer\s+price|one-time\s+purchase|cost)"
        rf"[^₹$€£¥0-9]{{0,45}}{currency_pattern}\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        rf"{currency_pattern}\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:current\s+price|sale\s+price|deal)",
    )
    values = []
    for pattern in patterns:
        for number in re.findall(pattern, text, re.I):
            try:
                values.append(float(number.replace(",", "")))
            except ValueError:
                continue
    return min(values, default=0)


def _is_direct_product_url(url: str, site: str) -> bool:
    lower = (url or "").lower()
    if not lower or any(part in lower for part in ("/search", "?k=", "?q=", "searchterm=")):
        return False
    if site == "amazon":
        return "/dp/" in lower or "/gp/product/" in lower
    return True


def _canonical_product_url(url: str, site: str) -> str:
    """Remove retailer tracking parameters while preserving the product page."""
    if site == "amazon":
        match = re.search(r"^(https?://[^/]+)(?:/[^?]*)?/dp/([A-Z0-9]{10})", url, re.I)
        if match:
            return f"{match.group(1)}/dp/{match.group(2).upper()}"
    return url


def _matches_product(result: dict, product: str) -> bool:
    """Keep a search result in the requested product category."""
    generic = {
        "a", "an", "the", "me", "some", "product", "products", "item", "items",
        "stuff", "thing", "things",
    }

    def terms(value: str) -> list[str]:
        words = re.findall(r"[a-z0-9]+", value.lower())
        normalized = []
        for word in words:
            if word in generic:
                continue
            if word in {"heated", "heating", "electric"}:
                word = "heated"
            elif len(word) > 3 and word.endswith("s"):
                word = word[:-1]
            normalized.append(word)
        return normalized

    requested = terms(product)
    if not requested:
        return True
    # Use the title, not the body: retailer pages contain carousels for many
    # unrelated products, which can otherwise create false category matches.
    haystack = set(terms(str(result.get("title") or "")))
    # Require the category and its meaningful modifiers. A small normalization
    # maps "electric" to "heated", while preventing adjacent items such as cat
    # scratchers or ordinary throw blankets from leaking into recommendations.
    return all(term in haystack for term in requested)


def _strip_wake_prefix(msg: str) -> str:
    return re.sub(r"^(?:hey\s+)?(?:jarvis|edith)[,.]?\s*", "", msg, flags=re.I).strip()


def _is_model_identity_query(message: str) -> bool:
    """Recognize model-status questions without spending an LLM call."""
    normalized = re.sub(r"[^a-z0-9\s-]", " ", str(message or "").lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if len(normalized) > 140:
        return False
    patterns = (
        r"\b(?:which|whihc|what) (?:api )?model (?:is this|am i (?:using|runn+ing|chatting to)|are you using)\b",
        r"^(?:which|whihc|what) model$",
        r"\bwhat (?:api )?model are you powered by\b",
        r"\bwhat are you powered by\b",
        r"\bmodel (?:is this|am i (?:using|runn+ing))\b",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def _model_identity_answer(preference: str) -> tuple[str, dict]:
    details = get_model_router().describe_selection(preference)
    provider = str(details.get("provider") or "automatic routing").title()
    label = str(details.get("label") or "No model available")
    model = str(details.get("model") or "")
    if details.get("selection") == "explicit":
        if not details.get("configured"):
            answer = (
                f"Your chat is set to **{label}** through **{provider}**, but that provider has no saved API key. "
                "Add the key in Settings or choose Auto."
            )
        else:
            answer = (
                f"Your chat is set to **{label}** through **{provider}**. "
                f"Model ID: `{model}`. Normal prompts use that exact selection."
            )
    elif details.get("configured"):
        answer = (
            f"**Auto** is selected. The most recently used route is **{label}** through **{provider}**"
            f"{f' (`{model}`)' if model else ''}. Auto may switch providers if one fails or reaches a limit."
        )
    else:
        answer = "No AI model provider is currently configured. Add one global API key in Settings."
    answer += " This model-status reply is generated locally, so it returns immediately and cannot hallucinate its identity."
    return answer, details


def _split_entity_list(phrase: str) -> list:
    phrase = re.sub(r"\s+and\s+", ", ", phrase, flags=re.I)
    return [e.strip().rstrip(".") for e in phrase.split(",") if e.strip()]


def _split_category_list(phrase: str) -> list:
    phrase = re.sub(r"\s+and\s+", ", ", phrase, flags=re.I)
    return [c.strip().rstrip(".").lower() for c in phrase.split(",") if c.strip()]


def _match_intelligence_command(raw_msg: str):
    """Returns (kind, data) for a recognized watchlist/intelligence/research
    command, or (None, None) if the message doesn't match one. Checked
    before Brain classification since these commands need deterministic
    routing, not LLM guessing, for a reliable demo."""
    msg = _strip_wake_prefix(raw_msg)

    m = re.match(r"^(?:monitor|track)\s+(.+?)(?:\s+for\s+(.+))?$", msg, re.I)
    if m:
        entities = _split_entity_list(m.group(1))
        categories = _split_category_list(m.group(2)) if m.group(2) else None
        if entities:
            return "monitor", {"entities": entities, "categories": categories}

    m = re.match(r"^stop\s+monitoring\s+(.+)$", msg, re.I)
    if m:
        return "unmonitor", {"phrase": m.group(1).strip().rstrip(".")}

    if re.match(r"^(?:show|list)\s+(?:me\s+)?my\s+watchlist", msg, re.I):
        return "show_watchlist", {}

    m = re.match(r"^what\s+sources\s+are\s+being\s+monitored\s+for\s+(.+)$", msg, re.I)
    if m:
        return "show_sources", {"entity": m.group(1).strip().rstrip("?.")}

    if re.match(r"^(?:scan\s+all\s+companies\s+now|run\s+all\s+watchlists|scan\s+all\b|scan\s+now)", msg, re.I):
        return "scan_all", {}

    m = re.match(r"^(?:show me\s+)?what\s+(?:changed|has changed)\s+with\s+(.+)$", msg, re.I)
    if m:
        return "live_query", {"query": raw_msg}

    # Two specific named entities -> structured side-by-side comparison.
    # Checked before the broad research-mission trigger so "Compare NVIDIA
    # and AMD" doesn't get swallowed by "compare the major ..." handling.
    m = re.match(r"^compare\s+(.+?)\s+and\s+(.+?)(?:\s+updates?|\s+changes?)?$", msg, re.I)
    if m and not re.match(r"^(?:the\s+)?(?:major|top|leading|biggest|largest)\b", m.group(1), re.I):
        def _strip_filler(phrase: str) -> str:
            return re.sub(r"^(?:recent|the|latest)\s+", "", phrase.strip(), flags=re.I).strip()
        entity_a, entity_b = _strip_filler(m.group(1)), _strip_filler(m.group(2))
        if entity_a and entity_b:
            return "compare_entities", {"entity_a": entity_a, "entity_b": entity_b}

    # Broad, open-ended research goals -> a research mission, not a specific
    # two-entity compare. Covers phrasing beyond a bare "research X" prefix.
    m = re.match(r"^(?:research|investigate|explore|analyze)\s+(.+)$", msg, re.I)
    if m:
        return "research_mission", {"query": m.group(1).strip()}

    if re.match(r"^compare\s+the\s+(?:major|top|leading|biggest|largest)\s+", msg, re.I):
        return "research_mission", {"query": raw_msg.strip()}

    if re.match(r"^find\s+the\s+most\s+important\s+", msg, re.I):
        return "research_mission", {"query": raw_msg.strip()}

    # Fallback: only route to the live-intelligence layer when the message
    # both smells like a "recent changes" question AND actually names a
    # watchlist entity — otherwise leave it to normal chat/realtime routing.
    if needs_live_data(msg) and matching_entities(msg):
        return "live_query", {"query": raw_msg}

    return None, None


async def _jarvis_stream(
    req: ChatRequest,
    ensured_session_id: str | None = None,
    cancel_event: threading.Event | None = None,
) -> AsyncGenerator[str, None]:
    t_start = time.perf_counter()
    session_id = ensured_session_id or chat_service.ensure_session(req.session_id)
    yield _sse({"session_id": session_id})

    raw_message = req.message or ""
    has_image = bool(req.imgbase64)
    clean_message = raw_message.replace(CAM_BYPASS_TOKEN, "").strip() or raw_message.strip()

    yield _sse({"activity": {"event": "query_detected", "message": clean_message[:200]}})

    history = chat_service.get_model_context(session_id)
    context_stats = chat_service.get_context_stats(session_id)
    if context_stats.get("compacted_turns", 0):
        yield _sse({"activity": {
            "event": "context_compacted",
            "route": "local",
            "message": (
                f"Compacted {context_stats['compacted_turns']} older turn(s) · "
                f"{context_stats.get('tokens', 0)} session-context tokens"
            ),
            "token_usage": context_stats,
        }})

    if _is_model_identity_query(clean_message):
        full_reply, details = _model_identity_answer(req.model_preference)
        yield _sse({"activity": {
            "event": "model_selected",
            "route": "local",
            "message": f"{details.get('label')} · {str(details.get('provider') or 'auto').title()}",
            "model": details.get("model"),
            "provider": details.get("provider"),
        }})
        yield _sse({"chunk": full_reply})
        chat_service.append_turn(session_id, clean_message, full_reply)
        memory_store.add_turn(session_id, clean_message, full_reply)
        yield _sse({"done": True})
        return

    # TrueForge owns conversational and agentic turns when enabled. Existing
    # deterministic commands and pending legacy confirmations remain local.
    pending_work_action = bool(
        req.mode == "work"
        and hasattr(work_mode_service, "_pending_for_session")
        and work_mode_service._pending_for_session(session_id)
    )
    if req.model_preference == "auto" and trueforge_service.should_route(req.mode, clean_message, pending_work_action):
        profile = trueforge_service.profile_for(req.mode, req.research_branch, clean_message)
        harness_health = await trueforge_service.health()
        if harness_health.get("ok") and edith_mcp is not None:
            images = list(req.imgbase64s)
            if req.imgbase64 and req.imgbase64 not in images:
                images.insert(0, req.imgbase64)
            yield _sse({"activity": {
                "event": "routing",
                "route": "trueforge",
                "profile": profile,
                "message": f"TrueForge is orchestrating the {profile} turn.",
            }})
            full_reply = ""
            harness_progressed = False
            try:
                async for item in trueforge_service.stream(session_id, profile, clean_message, images):
                    if "chunk" in item:
                        full_reply += str(item.get("chunk") or "")
                    if any(key in item for key in ("artifacts", "approval", "question", "auth_required")):
                        harness_progressed = True
                    activity = item.get("activity") if isinstance(item, dict) else None
                    if isinstance(activity, dict) and activity.get("event") in {
                        "tool_completed", "subagent_started", "subagent_completed"
                    }:
                        harness_progressed = True
                    yield _sse(item)
                if full_reply.strip():
                    if req.tts:
                        audio_b64 = await _tts_bytes_b64(full_reply)
                        if audio_b64:
                            yield _sse({"audio": audio_b64})
                    chat_service.append_turn(session_id, clean_message, full_reply)
                    memory_store.add_turn(session_id, clean_message, full_reply)
                yield _sse({"done": True})
                return
            except Exception as exc:
                logger.exception("[TRUEFORGE] Turn failed")
                error_text = str(exc)
                rate_limited = "429" in error_text or "rate limit" in error_text.lower()
                if harness_progressed or not trueforge_service.fallback_enabled:
                    message = (
                        "The model rate limit was reached after TrueForge began the task. "
                        "No automatic retry was made to avoid repeating tool actions. Please retry in about a minute."
                        if rate_limited else
                        "The TrueForge turn was interrupted after it began. No automatic legacy rerun was made to avoid repeating tool actions."
                    )
                    yield _sse({"activity": {
                        "event": "harness_paused" if rate_limited else "harness_error",
                        "route": "trueforge",
                        "message": message,
                        "error": error_text,
                    }})
                    if rate_limited:
                        yield _sse({"auto_resume": {
                            "reason": "rate_limit",
                            "after_seconds": 60,
                            "profile": profile,
                        }})
                    else:
                        yield _sse({"error": message})
                    yield _sse({"done": True})
                    return
                yield _sse({"activity": {
                    "event": "harness_fallback", "route": "legacy",
                    "message": "TrueForge failed before running tools; continuing with the existing EDITH engine.",
                    "error": error_text,
                }})
        elif trueforge_service.fallback_enabled:
            yield _sse({"activity": {
                "event": "harness_fallback", "route": "legacy",
                "message": "TrueForge is offline; continuing with the existing EDITH engine.",
            }})
        else:
            yield _sse({"error": "TrueForge is enabled but unavailable."})
            yield _sse({"done": True})
            return

    if req.mode == "research":
        research_model_preference = req.model_preference
        # Keep Auto provider-neutral in Homework too. Image understanding can
        # still use Gemini Vision, but the reasoning pass must be able to move
        # immediately to Groq/OpenRouter when Gemini is slow, disconnected, or
        # out of quota.
        normalized_history = [{"user": user, "assistant": assistant} for user, assistant in history]
        images = list(req.imgbase64s)
        if req.imgbase64 and req.imgbase64 not in images:
            images.insert(0, req.imgbase64)
        yield _sse({"activity": {"event": "planning", "message": "Preparing the Research Mode pipeline..."}})
        try:
            result = await asyncio.to_thread(
                research_mode_service.run,
                clean_message,
                req.research_branch,
                images,
                normalized_history,
                req.homework_output,
                [item.model_dump() for item in req.text_attachments],
                session_id,
                research_model_preference,
                cancel_event.is_set if cancel_event is not None else None,
            )
            for activity in result.get("activities", []):
                yield _sse({"activity": activity})
            if result.get("search_results"):
                yield _sse({"search_results": result["search_results"]})
            if result.get("artifacts"):
                yield _sse({"artifacts": result["artifacts"]})
            full_reply = result.get("reply") or "Research completed."
            yield _sse({"activity": {"event": "streaming_started", "route": "research"}})
            yield _sse({"chunk": full_reply})
            if req.tts:
                audio_b64 = await _tts_bytes_b64(full_reply)
                if audio_b64:
                    yield _sse({"audio": audio_b64})
            chat_service.append_turn(session_id, clean_message, full_reply)
            memory_store.add_turn(session_id, clean_message, full_reply)
            yield _sse({"done": True})
        except Exception as exc:
            logger.exception("[RESEARCH MODE] Pipeline failed")
            yield _sse({"error": str(exc)})
            yield _sse({"done": True})
        return

    if req.mode == "work":
        normalized_history = [{"user": user, "assistant": assistant} for user, assistant in history]
        try:
            work_images = list(req.imgbase64s)
            if req.imgbase64 and req.imgbase64 not in work_images:
                work_images.insert(0, req.imgbase64)
            if work_images or not work_mode_service._is_simple_browser_navigation(clean_message):
                yield _sse({"activity": {"event": "planning", "message": "Planning the Work Mode task..."}})
            result = await asyncio.to_thread(
                work_mode_service.run,
                clean_message,
                normalized_history,
                work_images,
                req.auto_approve_safe_work,
                session_id,
                req.model_preference,
                cancel_event.is_set if cancel_event is not None else None,
            )
            for activity in result.get("activities", []):
                yield _sse({"activity": activity})
            if result.get("artifacts"):
                yield _sse({"artifacts": result["artifacts"]})
            if result.get("actions"):
                yield _sse({"actions": result["actions"]})
            full_reply = result.get("reply") or "Work completed."
            yield _sse({"activity": {"event": "streaming_started", "route": "work"}})
            yield _sse({"chunk": full_reply})
            if req.tts:
                audio_b64 = await _tts_bytes_b64(full_reply)
                if audio_b64:
                    yield _sse({"audio": audio_b64})
            chat_service.append_turn(session_id, clean_message, full_reply)
            memory_store.add_turn(session_id, clean_message, full_reply)
            yield _sse({"done": True})
        except Exception as exc:
            logger.exception("[WORK] Work Mode failed")
            yield _sse({"error": str(exc)})
            yield _sse({"done": True})
        return

    key_index = rotators["brain"].next_index()

    full_reply = ""
    search_payload = None

    scrape_match = None
    scrape_entity_phrase = None
    shopping_match = None
    intel_kind, intel_data = None, None
    if not has_image:
        shopping_match = _match_shopping_request(clean_message, history)
        scrape_match = re.match(
            r"^(?:scrape|extract data (?:from|for)|get data (?:from|for)|collect data (?:from|for)|"
            r"pull data (?:from|for))\s+(https?://\S+)",
            clean_message, re.I,
        )
        if not scrape_match:
            entity_m = re.match(
                r"^(?:scrape|extract data (?:from|for)|get data (?:from|for)|collect data (?:from|for)|"
                r"pull data (?:from|for))\s+(.+)$",
                clean_message, re.I,
            )
            if entity_m:
                scrape_entity_phrase = entity_m.group(1).strip().rstrip(".,!?")
            else:
                intel_kind, intel_data = _match_intelligence_command(clean_message)

    try:
        if shopping_match:
            site = shopping_match["site"]
            product = shopping_match["product"]
            budget = shopping_match.get("budget")
            domain, search_base = _shopping_site_target(site, budget)
            review_focus = "most reviewed high number of customer ratings" if shopping_match.get("prioritize_reviews") else ""
            if budget:
                budget_terms = f"under {budget['label']} {budget['currency']}"
                queries = [
                    f"{product} {budget_terms} customer ratings site:{domain}",
                    f"{product} price below {budget['amount']:g} {budget['currency']} reviews site:{domain}",
                    f"{product} {budget['symbol']}{max(1, budget['amount'] - 1):g} site:{domain}",
                    f"{product} {budget['symbol']}{max(1, budget['amount'] * .75):g} site:{domain}",
                    f"{product} {review_focus} affordable site:{domain}",
                ]
            else:
                queries = [
                    f"{product} {review_focus} site:{domain}".strip(),
                    f"{product} bestseller customer reviews ratings site:{domain}".strip(),
                ]
            query = queries[0]
            yield _sse({"activity": {"event": "decision", "query_type": "shopping",
                                      "reasoning": f"direct {site} product search"
                                      + (f" within {budget['label']}" if budget else ""), "elapsed_ms": 0}})
            yield _sse({"activity": {"event": "searching_web", "query": query}})
            payloads = await asyncio.gather(*[
                asyncio.to_thread(realtime_service.search, search_query, 10, index == 0)
                for index, search_query in enumerate(queries)
            ])
            search_payload = payloads[0]
            candidate_map = {}
            for payload in payloads:
                for result in payload.get("results", []):
                    raw_url = result.get("url") or ""
                    if domain not in raw_url.lower() or not _is_direct_product_url(raw_url, site):
                        continue
                    if not _matches_product(result, product):
                        continue
                    canonical_url = _canonical_product_url(raw_url, site)
                    existing = candidate_map.get(canonical_url)
                    if not existing or float(result.get("score") or 0) > float(existing.get("score") or 0):
                        candidate_map[canonical_url] = {**result, "url": canonical_url}
            candidates = list(candidate_map.values())
            for result in candidates:
                result["review_count"] = _extract_review_count(result)
                result["price"] = _extract_price(result, budget["currency"]) if budget else 0
            if budget:
                candidates = [
                    result for result in candidates
                    if not result.get("price") or result["price"] <= budget["amount"]
                ]
            candidates.sort(key=lambda result: (
                1 if (not budget or result.get("price")) else 0,
                result.get("review_count", 0), float(result.get("score") or 0)
            ), reverse=True)
            product_results = candidates[:3]
            links = [
                {
                    "title": result.get("title") or f"View on {site.title()}",
                    "url": result.get("url"),
                    "context": " • ".join(filter(None, (
                        (f"{budget['symbol']}{result['price']:g} price shown in search evidence"
                         if budget and result.get("price") else
                         (f"Price not exposed — verify it is within {budget['label']}" if budget else "")),
                        (f"{result['review_count']:,} customer ratings/reviews shown in search evidence"
                         if result.get("review_count") else "Review count not exposed — verify on retailer"),
                    ))),
                }
                for result in product_results
                if result.get("url")
            ]
            budget_suffix = f" under {budget['label']}" if budget else ""
            public_results = [
                {**result, "content": (result.get("content") or "")[:1500]}
                for result in product_results
            ]
            display_payload = {
                "query": f"{product}{budget_suffix} on {site.title()}",
                "answer": f"Direct {site.title()} links for {product}.",
                "results": public_results,
            }
            yield _sse({"search_results": display_payload})
            yield _sse({"actions": {"links": links}})
            yield _sse({"activity": {"event": "search_completed",
                                      "message": f"{len(links)} direct link(s) ready"}})
            evidenced = sum(1 for result in product_results if result.get("review_count"))
            priced = sum(1 for result in product_results if result.get("price"))
            evidence_note = (
                f" I ranked them by the review counts exposed in the live search evidence ({evidenced} verified)."
                if evidenced else
                " Review totals were not exposed in the search snippets, so I have not invented them—please verify the current counts on the product pages."
            )
            if links:
                full_reply = (
                    f"Here are {len(links)} direct {site.title()} product option{'s' if len(links) != 1 else ''} for {product}"
                    f"{budget_suffix}, with price and review context."
                    f"{f' {priced} price point(s) were verified from live evidence.' if budget and priced else ''}"
                    f"{evidence_note}"
                )
            else:
                full_reply = (
                    f"I couldn't verify a direct {site.title()} product page for {product}{budget_suffix} right now. "
                    "I won't substitute a generic retailer search page; please try again in a moment."
                )
            yield _sse({"activity": {"event": "streaming_started", "route": "realtime"}})
            yield _sse({"chunk": full_reply})
            if req.tts:
                audio_b64 = await _tts_bytes_b64(full_reply)
                if audio_b64:
                    yield _sse({"audio": audio_b64})

        elif scrape_match or scrape_entity_phrase:
            target_url = None
            if scrape_match:
                target_url = scrape_match.group(1).rstrip(".,!?)")
            else:
                yield _sse({"activity": {"event": "decision", "query_type": "scrape",
                                          "reasoning": "scrape command detected (no URL given)", "elapsed_ms": 0}})
                yield _sse({"activity": {"event": "scrape_triggered",
                                          "message": f"Looking up the official page for {scrape_entity_phrase}..."}})
                target_url = await asyncio.to_thread(discover_source_url, scrape_entity_phrase, "website")
                if not target_url:
                    answer = (f"I couldn't find an official page for '{scrape_entity_phrase}' to scrape — "
                              f"try giving me a direct URL instead (e.g. 'scrape https://...').")
                    full_reply = answer
                    yield _sse({"activity": {"event": "scrape_completed", "message": "No source found"}})
                    yield _sse({"activity": {"event": "streaming_started", "route": "scrape"}})
                    yield _sse({"chunk": answer})
                    chat_service.append_turn(session_id, clean_message, full_reply)
                    memory_store.add_turn(session_id, clean_message, full_reply)
                    yield _sse({"done": True})
                    return

            yield _sse({"activity": {"event": "decision", "query_type": "scrape",
                                      "reasoning": "scrape command detected", "elapsed_ms": 0}})
            yield _sse({"activity": {"event": "scrape_triggered",
                                      "message": f"Reading {target_url}"}})

            result = await asyncio.to_thread(web_reader.scrape_with_self_healing, target_url)

            if result.healed:
                yield _sse({"activity": {"event": "scrape_self_healing",
                                          "message": "Trying a secondary webpage-reading method"}})
            if result.success:
                yield _sse({"activity": {"event": "scrape_completed",
                                          "message": f"Source: {result.source}"}})
                # Preserve structured field names when a reader provides them so the summarizer
                # can distinguish titles, descriptions, prices, and other
                # values instead of receiving one flattened text dump.
                snippet = (
                    json.dumps(result.data[:20], ensure_ascii=False)
                    if isinstance(result.data, list) and result.data
                    else (result.text or "").strip()
                )
                answer = await asyncio.to_thread(
                    groq_service.summarize_scrape,
                    snippet,
                    target_url,
                )
            else:
                yield _sse({"activity": {"event": "scrape_completed", "message": "Failed"}})
                answer = f"Couldn't scrape {target_url}: {result.error}"

            full_reply = answer
            yield _sse({"activity": {"event": "streaming_started", "route": "scrape"}})
            yield _sse({"chunk": answer})
            if req.tts:
                audio_b64 = await _tts_bytes_b64(answer)
                if audio_b64:
                    yield _sse({"audio": audio_b64})

        elif intel_kind:
            yield _sse({"activity": {"event": "decision", "query_type": "intelligence",
                                      "reasoning": intel_kind, "elapsed_ms": 0}})
            answer = ""

            if intel_kind == "monitor":
                entities, categories = intel_data["entities"], intel_data["categories"]
                added = []
                for name in entities:
                    entry = await asyncio.to_thread(watchlist_service.add_watchlist, name, categories)
                    added.append(entry["name"])
                yield _sse({"activity": {"event": "watchlist_updated",
                                          "message": f"Now monitoring: {', '.join(added)}"}})
                cat_note = f" (categories: {', '.join(categories)})" if categories else ""
                answer = f"Added to watchlist: {', '.join(added)}{cat_note}. I'll build up snapshots as I scan them."

            elif intel_kind == "unmonitor":
                removed = await asyncio.to_thread(watchlist_service.remove_watchlist, intel_data["phrase"])
                answer = f"Stopped monitoring {intel_data['phrase']}." if removed else \
                    f"I couldn't find '{intel_data['phrase']}' on your watchlist."

            elif intel_kind == "show_watchlist":
                entries = watchlist_service.get_watchlists()
                if not entries:
                    answer = "Your watchlist is empty. Try 'Monitor <company>' to add one."
                else:
                    lines = [f"- {e['name']}: {', '.join(e['categories'])}" for e in entries]
                    answer = "Your watchlist:\n" + "\n".join(lines)

            elif intel_kind == "show_sources":
                entry = watchlist_service.get_watchlist(intel_data["entity"])
                if not entry:
                    answer = f"'{intel_data['entity']}' isn't on your watchlist."
                elif not entry.get("sources"):
                    answer = f"No sources discovered yet for {entry['name']} — run a scan first."
                else:
                    lines = [f"- {s['category']}: {s['url']}" for s in entry["sources"]]
                    answer = f"Sources for {entry['name']}:\n" + "\n".join(lines)

            elif intel_kind == "scan_all":
                yield _sse({"activity": {"event": "scan_started", "message": "Scanning all watchlist entries..."}})
                results = await asyncio.to_thread(watchlist_service.run_all_watchlists)
                total_changes = sum(len(r.get("changes", [])) for res in results for r in res.get("results", []))
                yield _sse({"activity": {"event": "scan_completed",
                                          "message": f"{len(results)} entities scanned, {total_changes} change(s) found"}})
                source_links = []
                seen_sources = set()
                for entity_result in results:
                    for category_result in entity_result.get("results", []):
                        for change in category_result.get("changes", []):
                            source_url = change.get("source_url")
                            if not source_url or source_url in seen_sources:
                                continue
                            seen_sources.add(source_url)
                            source_links.append({
                                "title": f"Evidence for {change.get('entity') or entity_result.get('entity', 'detected change')}",
                                "url": source_url,
                                "context": f"Source page · {change.get('category') or category_result.get('category', 'monitored data')}",
                            })
                if source_links:
                    yield _sse({"actions": {"links": source_links[:6]}})
                answer = format_scan_change_report(results) if results \
                    else "Your watchlist is empty, nothing to scan."

            elif intel_kind == "live_query":
                yield _sse({"activity": {"event": "searching_web", "message": "Checking monitored evidence..."}})
                live_result = await asyncio.to_thread(answer_live_query, intel_data["query"])
                if live_result.get("used_tavily_fallback"):
                    yield _sse({"activity": {"event": "search_completed", "message": "Used live web search (no monitored data yet)"}})
                else:
                    yield _sse({"activity": {"event": "search_completed", "message": "Answered from monitored snapshots"}})
                answer = live_result["answer"]

            elif intel_kind == "compare_entities":
                yield _sse({"activity": {"event": "searching_web",
                                          "message": f"Comparing {intel_data['entity_a']} vs {intel_data['entity_b']}..."}})
                comparison = await asyncio.to_thread(compare_entities, intel_data["entity_a"], intel_data["entity_b"])
                yield _sse({"activity": {"event": "search_completed",
                                          "message": f"{len(comparison.get('rows', []))} shared categor(y/ies) compared"}})
                answer = comparison["narrative"]

            elif intel_kind == "research_mission":
                mission = await asyncio.to_thread(research_service.start_mission, intel_data["query"])
                yield _sse({"activity": {"event": "mission_started",
                                          "message": f"Research mission started: {intel_data['query']}"}})
                answer = (f"Started a research mission on '{intel_data['query']}' "
                          f"(mission_id: {mission['mission_id']}). Ask me for the mission status "
                          f"to read the report once it is done.")

            full_reply = answer or "Done."
            yield _sse({"activity": {"event": "streaming_started", "route": "intelligence"}})
            yield _sse({"chunk": full_reply})
            if req.tts:
                audio_b64 = await _tts_bytes_b64(full_reply)
                if audio_b64:
                    yield _sse({"audio": audio_b64})

        elif has_image:
            route = "camera"
            yield _sse({"activity": {"event": "decision", "query_type": "camera",
                                      "reasoning": "image attached", "elapsed_ms": 0}})
            yield _sse({"activity": {"event": "vision_analyzing", "message": "Analyzing image..."}})
            answer = await asyncio.to_thread(vision_service.analyze, req.imgbase64, clean_message)
            full_reply = answer
            yield _sse({"activity": {"event": "streaming_started", "route": "vision"}})
            yield _sse({"chunk": answer})
            if req.tts:
                audio_b64 = await _tts_bytes_b64(answer)
                if audio_b64:
                    yield _sse({"audio": audio_b64})

        else:
            category, method, ms = brain.classify_primary(clean_message, history, key_index)
            task_types = []
            yield _sse({"activity": {"event": "decision", "query_type": category,
                                      "reasoning": method, "elapsed_ms": ms}})
            yield _sse({"activity": {"event": "routing", "route": category}})

            if category in ("task", "mixed"):
                task_types, tmethod, tms = brain.classify_task(clean_message, history, key_index)
                yield _sse({"activity": {"event": "intent_classified", "intent": ", ".join(task_types) or "open"}})

                intents = brain.extract_task_payloads(clean_message, task_types, history)
                yield _sse({"activity": {"event": "tasks_executing", "message": f"Running {len(intents)} task(s)..."}})

                # Writing is a conversational generation result in Edit mode,
                # not a browser action or a hidden file job.  If classification
                # produced no usable task, fail safely into the same response
                # path instead of inventing an `open google.com` action.
                if category == "task" and (
                    not intents or all(intent == INTENT_CONTENT for intent, _payload in intents)
                ):
                    yield _sse({"activity": {"event": "streaming_started", "route": "general"}})
                    first = True
                    async for piece in groq_service.stream_reply(
                        clean_message, history, rotators["chat"].next_index(), req.model_preference
                    ):
                        if first:
                            yield _sse({"activity": {"event": "first_chunk", "route": "general",
                                                      "elapsed_ms": int((time.perf_counter() - t_start) * 1000)}})
                            first = False
                        full_reply += piece
                        yield _sse({"chunk": piece})
                    yield _sse({"activity": {"event": "tasks_completed", "message": "Content generated"}})
                    if req.tts and full_reply.strip():
                        audio_b64 = await _tts_bytes_b64(full_reply)
                        if audio_b64:
                            yield _sse({"audio": audio_b64})
                    chat_service.append_turn(session_id, clean_message, full_reply)
                    memory_store.add_turn(session_id, clean_message, full_reply)
                    yield _sse({"done": True})
                    return

                actions, background_jobs = build_actions_and_background(intents)

                dispatched_tasks = []
                for job in background_jobs:
                    use_previous_image = (
                        job["type"] == "generate image"
                        and brain._looks_like_image_revision(clean_message, history)
                    )
                    task_id = task_manager.submit(
                        job["type"],
                        job["prompt"],
                        job["label"],
                        session_id=session_id,
                        use_previous_image=use_previous_image,
                    )
                    dispatched_tasks.append({"task_id": task_id, "type": job["type"], "label": job["label"]})

                if actions:
                    yield _sse({"actions": actions})
                    yield _sse({"activity": {"event": "actions_emitted", "message": f"{len(actions)} action group(s) sent"}})
                if dispatched_tasks:
                    yield _sse({"background_tasks": dispatched_tasks})
                    yield _sse({"activity": {"event": "background_dispatched",
                                              "message": f"{len(dispatched_tasks)} background job(s) started"}})

                yield _sse({"activity": {"event": "tasks_completed", "message": "Done"}})

                if category == "mixed":
                    yield _sse({"activity": {"event": "streaming_started", "route": "chat"}})
                    async for piece in groq_service.stream_reply(
                        clean_message, history, rotators["chat"].next_index(), req.model_preference
                    ):
                        full_reply += piece
                        yield _sse({"chunk": piece})
                else:
                    if dispatched_tasks and all(task["type"] == "generate image" for task in dispatched_tasks):
                        ack = "I’m generating the image now. The preview will appear as soon as the verified image file is ready."
                    else:
                        ack = "Done." if (actions or dispatched_tasks) else "On it."
                    full_reply = ack
                    yield _sse({"chunk": ack})

                if req.tts and full_reply.strip():
                    audio_b64 = await _tts_bytes_b64(full_reply)
                    if audio_b64:
                        yield _sse({"audio": audio_b64})

            elif category == "realtime":
                yield _sse({"activity": {"event": "extracting_query", "message": "Parsing your question for search..."}})
                query = realtime_service.extract_query(clean_message, history, key_index)
                yield _sse({"activity": {"event": "searching_web", "query": query}})
                search_payload = realtime_service.search(query)
                yield _sse({"search_results": search_payload})
                yield _sse({"activity": {"event": "search_completed", "message": f"{len(search_payload.get('results', []))} result(s) found"}})

                yield _sse({"activity": {"event": "streaming_started", "route": "realtime"}})
                first = True
                async for piece in realtime_service.stream_reply(
                    clean_message, search_payload, history, rotators["chat"].next_index(), req.model_preference
                ):
                    if first:
                        yield _sse({"activity": {"event": "first_chunk", "route": "realtime",
                                                  "elapsed_ms": int((time.perf_counter() - t_start) * 1000)}})
                        first = False
                    full_reply += piece
                    yield _sse({"chunk": piece})

                if req.tts and full_reply.strip():
                    audio_b64 = await _tts_bytes_b64(full_reply)
                    if audio_b64:
                        yield _sse({"audio": audio_b64})

            else:  # general / camera-phrase-without-image fallback
                yield _sse({"activity": {"event": "context_retrieved", "message": "Knowledge base ready"}})
                yield _sse({"activity": {"event": "streaming_started", "route": "general"}})
                first = True
                async for piece in groq_service.stream_reply(
                    clean_message, history, rotators["chat"].next_index(), req.model_preference
                ):
                    if first:
                        yield _sse({"activity": {"event": "first_chunk", "route": "general",
                                                  "elapsed_ms": int((time.perf_counter() - t_start) * 1000)}})
                        first = False
                    full_reply += piece
                    yield _sse({"chunk": piece})

                if req.tts and full_reply.strip():
                    audio_b64 = await _tts_bytes_b64(full_reply)
                    if audio_b64:
                        yield _sse({"audio": audio_b64})

        chat_service.append_turn(session_id, clean_message, full_reply)
        memory_store.add_turn(session_id, clean_message, full_reply)

        yield _sse({"done": True})

    except Exception as e:
        logger.exception("[MAIN] Stream failed")
        yield _sse({"error": str(e)})
        yield _sse({"done": True})


@app.post("/chat/jarvis/stream")
async def chat_jarvis_stream(req: ChatRequest):
    session_id = chat_service.ensure_session(req.session_id)

    async def _tracked_stream() -> AsyncGenerator[str, None]:
        current = asyncio.current_task()
        previous = _active_chat_streams.get(session_id)
        previous_cancel_event = _active_chat_cancel_events.get(session_id)
        if previous_cancel_event is not None:
            previous_cancel_event.set()
        if previous and previous is not current and not previous.done():
            previous.cancel()
        cancel_event = threading.Event()
        if current is not None:
            _active_chat_streams[session_id] = current
        _active_chat_cancel_events[session_id] = cancel_event
        try:
            async for event in _jarvis_stream(req, ensured_session_id=session_id, cancel_event=cancel_event):
                yield event
        except asyncio.CancelledError:
            logger.info("[CHAT] Cancelled active response for session %s", session_id)
            return
        finally:
            if _active_chat_streams.get(session_id) is current:
                _active_chat_streams.pop(session_id, None)
            if _active_chat_cancel_events.get(session_id) is cancel_event:
                _active_chat_cancel_events.pop(session_id, None)

    return StreamingResponse(_tracked_stream(), media_type="text/event-stream")


# --- Static frontend (mounted last so API routes above take priority) ---
if edith_mcp is not None:
    app.mount("/mcp", edith_mcp.streamable_http_app())

if (FRONTEND_DIR / "viewer.html").exists():
    from fastapi.responses import FileResponse

    @app.get("/app/viewer.html")
    async def viewer_page():
        return FileResponse(str(FRONTEND_DIR / "viewer.html"))

app.mount("/app/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
