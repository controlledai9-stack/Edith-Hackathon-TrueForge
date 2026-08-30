from __future__ import annotations

import base64
import json
import logging
import re
import secrets
import config
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from config import DATA_DIR, VISION_MAX_IMAGE_BYTES
from app.plugins.registry import get_plugin_registry
from app.services.gemini_image_service import generate_gemini_image
from app.services.model_router import get_model_router

logger = logging.getLogger("J.A.R.V.I.S")
# Kept as a compatibility alias for older tests/extensions; routing itself
# reads the live values from config through ModelRouter.
GROQ_API_KEYS = config.GROQ_API_KEYS


class WorkModeService:
    _PENDING_PATH = DATA_DIR / "work_mode" / "pending_session_actions.json"

    def __init__(self) -> None:
        self.registry = get_plugin_registry()
        self._pending_lock = RLock()
        self._pending_by_session = self._load_pending_confirmations()

    def _load_pending_confirmations(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self._PENDING_PATH.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save_pending_confirmations(self) -> None:
        self._PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._PENDING_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._pending_by_session, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self._PENDING_PATH)

    @staticmethod
    def _is_confirmation(message: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]+", " ", str(message).lower()).strip()
        if re.search(r"\b(?:cancel|stop|reject|no|don t|do not|not yet)\b", normalized):
            return False
        return bool(re.search(r"\b(?:confirm|confirmed|yes|proceed|approve|approved|post|publish|go ahead)\b", normalized))

    @staticmethod
    def _is_cancellation(message: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]+", " ", str(message).lower()).strip()
        return bool(re.search(r"\b(?:cancel|stop|reject|don t|do not|not yet)\b", normalized))

    def _set_pending(self, session_id: str, value: dict[str, Any] | None) -> None:
        with self._pending_lock:
            if value is None:
                self._pending_by_session.pop(session_id, None)
            else:
                self._pending_by_session[session_id] = value
            self._save_pending_confirmations()

    def _resolve_pending_confirmation(self, session_id: str, request: str) -> dict[str, Any] | None:
        with self._pending_lock:
            pending = self._pending_by_session.get(session_id)
        if not pending:
            return None
        if self._is_cancellation(request):
            plugin_id = "linkedin" if pending.get("tool_name") == "linkedin_publish" else "browser_operator"
            plugin = self.registry.get_plugin(plugin_id)
            if plugin and hasattr(plugin, "cancel_pending"):
                plugin.cancel_pending(pending["confirmation_id"])
            self._set_pending(session_id, None)
            return {"reply": "The pending browser action was cancelled. Nothing was posted or changed.", "artifacts": [], "activities": []}
        if not self._is_confirmation(request):
            return None
        task = pending["task"]
        tool_name = pending.get("tool_name", "browser_task")
        if tool_name == "linkedin_publish":
            arguments = {
                "caption": task["caption"],
                "image_path": task["image_path"],
                "confirmed": True,
                "confirmation_id": pending["confirmation_id"],
            }
        else:
            arguments = {
                "url": task["url"],
                "objective": task["objective"],
                "action_type": task["action_type"],
                "file_paths": [item["path"] for item in task.get("files", [])],
                "context": task.get("context", ""),
                "confirmed": True,
                "confirmation_id": pending["confirmation_id"],
            }
        result = self.registry.execute(tool_name, arguments).as_dict()
        if result.get("success"):
            self._set_pending(session_id, None)
        browser_task = (result.get("data") or {}).get("browser_task") if isinstance(result.get("data"), dict) else None
        browser_job = (result.get("data") or {}).get("browser_job") if isinstance(result.get("data"), dict) else None
        actions: dict[str, Any] = {}
        if browser_task:
            actions["browser_tasks"] = [browser_task]
        if browser_job:
            actions["browser_jobs"] = [browser_job]
        return {
            "reply": result.get("message") or "The confirmed browser action is ready.",
            "artifacts": result.get("artifacts") or [],
            "activities": [{"event": "tool_completed" if result.get("success") else "tool_failed", "message": result.get("message"), "tool": tool_name}],
            "actions": actions,
        }

    @staticmethod
    def _is_linkedin_publish_request(message: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]+", " ", str(message).lower())
        if "linkedin" not in normalized:
            return False
        explicit_publish = re.search(r"\b(?:post|publish|upload|share|put|add)\b", normalized)
        content_to_linkedin = re.search(
            r"\b(?:image|photo|png|jpg|jpeg|video|caption|context|content)\b.*\b(?:on|to)\s+(?:my\s+)?linkedin\b",
            normalized,
        )
        linked_content = re.search(
            r"\b(?:on|to)\s+(?:my\s+)?linkedin\b.*\b(?:image|photo|png|jpg|jpeg|video|caption|context|content)\b",
            normalized,
        )
        return bool(explicit_publish or content_to_linkedin or linked_content)

    @staticmethod
    def _wants_generated_linkedin_image(message: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]+", " ", str(message).lower())
        return bool(
            "linkedin" in normalized
            and re.search(r"\b(?:generate|genrate|create|make|design|draw)\b.{0,50}\b(?:image|photo|picture|graphic|visual)\b", normalized)
        )

    @staticmethod
    def _is_image_generation_request(message: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]+", " ", str(message).lower())
        return bool(re.search(r"\b(?:generate|genrate|create|make|design|draw)\b.{0,70}\b(?:image|photo|picture|graphic|visual)\b", normalized))

    @staticmethod
    def _linkedin_image_prompt(request: str) -> str:
        cleaned = re.sub(
            r"\b(?:and|then)\s+(?:also\s+)?(?:generate|genrate|write|create)\s+(?:a\s+)?(?:caption|context|text)\b.*$",
            "",
            str(request),
            flags=re.I,
        )
        cleaned = re.sub(r"\b(?:and|then)\s+(?:post|publish|upload|share)\b.*$", "", cleaned, flags=re.I)
        cleaned = re.sub(r"^\s*(?:please\s+)?(?:generate|genrate|create|make|design|draw)\s+(?:me\s+)?(?:an?\s+)?(?:image|photo|picture|graphic|visual)\s*(?:about|on|of)?\s*", "", cleaned, flags=re.I)
        topic = cleaned.strip(" .,;:-") or "modern artificial intelligence development and rapid growth"
        return (
            f"Professional editorial illustration for LinkedIn about {topic}. "
            "Modern artificial intelligence, accelerating innovation, upward growth, luminous neural networks, "
            "clean premium technology aesthetic, blue and violet cinematic lighting, square composition, no text, no logos, no watermark."
        )

    def _generate_linkedin_image(self, request: str) -> tuple[str, dict[str, str]]:
        return generate_gemini_image(self._linkedin_image_prompt(request), "linkedin_generated")

    @staticmethod
    def _work_mode_linkedin_caption() -> str:
        return (
            "I’ve now created Work Mode in E.D.I.T.H.—and it’s completely working. 🚀\n\n"
            "Work Mode can:\n"
            "• Create polished PowerPoint presentations (PPT)\n"
            "• Build formatted Excel spreadsheets and charts\n"
            "• Create PDFs and work with PDF content\n"
            "• Draft professional Word documents\n"
            "• Create Jupyter/Google Colab-ready notebooks\n"
            "• Build static websites and site packages\n"
            "• Search the web and read webpages\n"
            "• Turn information into charts and visualizations\n"
            "• Work with files and combine multiple tools into one workflow\n"
            "• Connect with GitHub and Google services such as Gmail, Drive, Calendar, and Tasks\n"
            "• Prepare browser-based tasks for other websites with confirmation controls\n\n"
            "This turns E.D.I.T.H. from a chat assistant into a practical execution workspace.\n\n"
            "#AI #Productivity #Automation #WorkMode #EDITH"
        )

    @staticmethod
    def _research_homework_linkedin_caption() -> str:
        return (
            "I’ve now created Research Mode in E.D.I.T.H.—a focused workspace for deep research, visual evidence, organized notes, and step-by-step problem solving. 🚀\n\n"
            "Research Mode can:\n"
            "• Research topics across the web and synthesize useful findings\n"
            "• Read documents, notes, webpages, and uploaded evidence\n"
            "• Scan one or several question screenshots with vision\n"
            "• Organize screenshots in a Snap Queue for batch solving\n"
            "• Produce clean, readable, step-by-step solutions on the solution whiteboard\n"
            "• Render equations and mathematical symbols properly\n"
            "• Keep the whiteboard and AI assistant in separate, resizable panels\n"
            "• Answer sidebar questions without changing the solution board or creating unnecessary files\n"
            "• Build one cumulative, editable research file for the current quiz or assignment\n"
            "• Record each question’s type, method, and formulas used\n"
            "• Maintain a formula index for the complete question set\n"
            "• Store uploaded evidence and generated study records in an organized workspace\n"
            "• Use web research, documents, notes, vision, and reasoning when the task needs them\n\n"
            "It turns E.D.I.T.H. into a focused research workspace—not just another blank AI chat screen.\n\n"
            "#AI #ResearchMode #HomeworkMode #EdTech #Productivity #EDITH"
        )

    @staticmethod
    def _linkedin_topic(request: str, history: list[dict] | None = None) -> str:
        current = str(request or "").lower()
        user_context = "\n".join(str(turn.get("user") or "") for turn in (history or [])[-6:]).lower()
        combined = f"{current}\n{user_context}"
        if re.search(r"\b(?:research|homework)\b", current) or (
            re.search(r"\b(?:same|that|previous)\s+context\b", current)
            and re.search(r"\b(?:research|homework)\b", combined)
        ):
            return "research_homework"
        if re.search(r"\bwork\s+mode\b", current) or re.search(r"\bwork\s+mode\b", combined):
            return "work"
        return "custom"

    def _linkedin_caption_for_request(
        self,
        request: str,
        history: list[dict] | None,
        client: Any,
    ) -> tuple[str, str]:
        normalized_request = re.sub(r"[^a-z0-9]+", " ", str(request).lower())
        if re.search(r"\b(?:just|only)\s+(?:the\s+)?(?:images?|photos?|pngs?|videos?)\b", normalized_request) or re.search(
            r"\b(?:without|no)\s+(?:a\s+)?(?:caption|context|text)\b", normalized_request
        ):
            return "", "media-only"
        topic = self._linkedin_topic(request, history)
        if topic == "research_homework":
            return self._research_homework_linkedin_caption(), "Research Mode"
        if topic == "work":
            return self._work_mode_linkedin_caption(), "Work Mode"

        user_context = "\n".join(
            f"- {str(turn.get('user')).strip()}" for turn in (history or [])[-6:] if turn.get("user")
        )
        try:
            response = client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": (
                        "Write the exact LinkedIn caption requested by the user. Plain text only: no Markdown bold, no code fences, no confirmation language. "
                        "Preserve the requested topic and facts; do not reuse an older post topic. Use concise paragraphs, an accurate feature list when requested, and 3-6 relevant hashtags."
                    )},
                    {"role": "user", "content": f"Current request:\n{request}\n\nRecent user instructions only:\n{user_context}"},
                ],
                temperature=0.2,
            )
            caption = str(response.choices[0].message.content or "").strip()
            if caption:
                return caption, "the requested update"
        except Exception as exc:
            logger.warning("[WORK] LinkedIn caption generation failed: %s", exc)
        return str(request).strip(), "the requested update"

    @staticmethod
    def _is_pending_revision(message: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]+", " ", str(message).lower())
        return bool(re.search(
            r"\b(?:change|update|replace|revise|modify|instead|same context|use the .*context|caption|context)\b",
            normalized,
        ))

    def _pending_for_session(self, session_id: str) -> dict[str, Any] | None:
        with self._pending_lock:
            pending = self._pending_by_session.get(session_id)
            return dict(pending) if isinstance(pending, dict) else None

    def _cancel_plugin_pending(self, pending: dict[str, Any]) -> None:
        plugin_id = "linkedin" if pending.get("tool_name") == "linkedin_publish" else "browser_operator"
        plugin = self.registry.get_plugin(plugin_id)
        if plugin and hasattr(plugin, "cancel_pending"):
            plugin.cancel_pending(str(pending.get("confirmation_id") or ""))

    @staticmethod
    def _pending_attachment_paths(pending: dict[str, Any]) -> list[str]:
        task = pending.get("task") or {}
        if pending.get("tool_name") == "linkedin_publish":
            return [str(task["image_path"])] if task.get("image_path") else []
        return [str(item["path"]) for item in task.get("files", []) if isinstance(item, dict) and item.get("path")]

    @staticmethod
    def _infer_browser_destination(message: str) -> str | None:
        explicit = re.search(r"https?://[^\s<>'\"]+", str(message), flags=re.IGNORECASE)
        if explicit:
            return explicit.group(0).rstrip(".,);]")
        normalized = str(message).lower()
        destinations = {
            "reddit": "https://www.reddit.com/submit",
            "linkedin": "https://www.linkedin.com/feed/",
            "instagram": "https://www.instagram.com/",
            "facebook": "https://www.facebook.com/",
            "twitter": "https://x.com/compose/post",
            " x ": "https://x.com/compose/post",
            "medium": "https://medium.com/new-story",
            "wordpress": "https://wordpress.com/posts",
            "youtube": "https://www.youtube.com/",
        }
        destination = next((url for name, url in destinations.items() if name in normalized), None)
        if destination and "youtube" in normalized and re.search(r"\b(?:upload|publish|post)\b", normalized):
            return "https://www.youtube.com/upload"
        return destination

    @staticmethod
    def _is_simple_browser_navigation(message: str) -> bool:
        """Recognize commands that only need a page opened, without model planning."""
        normalized = re.sub(r"\s+", " ", str(message).lower()).strip()
        starts_with_navigation = bool(re.match(
            r"^(?:please\s+)?(?:open|launch|visit|go\s+to)\b",
            normalized,
        ))
        has_mutating_action = bool(re.search(
            r"\b(?:post|publish|upload|submit|send|message|fill|edit|delete|remove|purchase|buy)\b",
            normalized,
        ))
        return starts_with_navigation and not has_mutating_action

    def _stage_universal_browser_task(
        self,
        session_id: str,
        request: str,
        attachment_paths: list[str],
        activities: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        url = self._infer_browser_destination(request)
        normalized = str(request).lower()
        if not url or not re.search(r"\b(?:post|publish|upload|submit|send|message|fill|create|open|launch|visit|read|check)\b", normalized):
            return None
        if re.search(r"\b(?:post|publish|share)\b", normalized): action = "publish"
        elif "upload" in normalized: action = "upload"
        elif re.search(r"\b(?:send|message)\b", normalized): action = "message"
        elif "submit" in normalized: action = "submit"
        elif re.search(r"\b(?:read|check)\b", normalized): action = "read"
        else: action = "navigate"
        activity_log = list(activities or [])
        activity_log.append({"event": "tool_started", "message": "Preparing the universal browser workflow...", "tool": "browser_task"})
        result = self.registry.execute("browser_task", {
            "url": url,
            "objective": request,
            "action_type": action,
            "file_paths": attachment_paths,
            "context": request,
            "confirmed": False,
        }).as_dict()
        activity_log.append({"event": "tool_completed" if result.get("success") else "tool_failed", "message": result.get("message"), "tool": "browser_task"})
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        confirmation_id = data.get("confirmation_id")
        pending_task = data.get("pending_browser_task")
        if result.get("confirmation_required") and confirmation_id and pending_task:
            self._set_pending(session_id, {"tool_name": "browser_task", "confirmation_id": confirmation_id, "task": pending_task})
        actions = {"browser_jobs": [data["browser_job"]]} if data.get("browser_job") else {}
        return {"reply": result.get("message") or "Universal Browser could not prepare the task.", "artifacts": result.get("artifacts") or [], "activities": activity_log, "confirmation": data if result.get("confirmation_required") else None, "actions": actions}

    def _stage_linkedin_post(
        self,
        session_id: str,
        attachment_paths: list[str],
        request: str,
        history: list[dict] | None,
        client: Any,
        activities: list[dict[str, Any]] | None = None,
        caption_override: str | None = None,
        subject_override: str | None = None,
    ) -> dict[str, Any]:
        activity_log = list(activities or [])
        if caption_override is None:
            caption, subject = self._linkedin_caption_for_request(request, history, client)
        else:
            caption, subject = caption_override, subject_override or "the requested update"
        if not caption and not attachment_paths:
            return {
                "reply": "Please provide text, images, or videos for the LinkedIn post.",
                "artifacts": [],
                "activities": activity_log,
            }
        linkedin = self.registry.get_plugin("linkedin")
        api_compatible = bool(caption) and len(attachment_paths) == 1 and Path(attachment_paths[0]).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}
        use_linkedin_api = bool(linkedin and linkedin.enabled and linkedin.connected and api_compatible)
        tool_name = "linkedin_publish" if use_linkedin_api else "browser_task"
        activity_log.append({"event": "tool_started", "message": "Preparing the LinkedIn post...", "tool": tool_name})
        if use_linkedin_api:
            result = self.registry.execute("linkedin_publish", {
                "caption": caption,
                "image_path": attachment_paths[0],
                "confirmed": False,
            }).as_dict()
        else:
            result = self.registry.execute("browser_task", {
                "url": "https://www.linkedin.com/feed/",
                "objective": f"Publish the approved {subject} announcement on LinkedIn",
                "action_type": "publish",
                "file_paths": attachment_paths[:5],
                "context": caption,
                "confirmed": False,
            }).as_dict()
        activity_log.append({
            "event": "tool_completed" if result.get("success") else "tool_failed",
            "message": result.get("message"),
            "tool": tool_name,
        })
        confirmation_data = result.get("data") if isinstance(result.get("data"), dict) else {}
        confirmation_id = confirmation_data.get("confirmation_id")
        pending_task = confirmation_data.get("pending_linkedin_post") if use_linkedin_api else confirmation_data.get("pending_browser_task")
        if result.get("confirmation_required") and confirmation_id and pending_task:
            self._set_pending(session_id, {"tool_name": tool_name, "confirmation_id": confirmation_id, "task": pending_task})
        return {
            "reply": result.get("message") or "I could not prepare the LinkedIn post.",
            "artifacts": result.get("artifacts") or [],
            "activities": activity_log,
            "confirmation": confirmation_data if result.get("confirmation_required") else None,
            "actions": {},
        }

    def _revise_pending_linkedin_post(
        self,
        session_id: str,
        request: str,
        history: list[dict] | None,
        attachment_paths: list[str],
        client: Any,
        activities: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        pending = self._pending_for_session(session_id)
        if not pending or not self._is_pending_revision(request):
            return None
        task = pending.get("task") or {}
        task_url = str(task.get("url") or "")
        if pending.get("tool_name") != "linkedin_publish" and "linkedin.com" not in task_url:
            return None

        preserved_files = attachment_paths or self._pending_attachment_paths(pending)
        caption, subject = self._linkedin_caption_for_request(request, history, client)
        self._cancel_plugin_pending(pending)
        self._set_pending(session_id, None)
        revised_activities = list(activities or [])
        revised_activities.append({
            "event": "pending_action_revised",
            "message": "Replaced the earlier LinkedIn draft while preserving its attached image.",
            "tool": "browser_task",
        })
        return self._stage_linkedin_post(
            session_id,
            preserved_files,
            request,
            history,
            client,
            revised_activities,
            caption_override=caption,
            subject_override=subject,
        )

    @staticmethod
    def _store_attachments(images: list[str] | None) -> list[str]:
        directory = DATA_DIR / "work_mode" / "uploads"
        directory.mkdir(parents=True, exist_ok=True)
        paths = []
        supplied = images or []
        if len(supplied) > 5:
            raise ValueError("Work Mode accepts up to five attachments per task")
        for index, encoded in enumerate(supplied, start=1):
            mime = ""
            duration = None
            value = encoded
            if encoded.startswith("data:") and "," in encoded:
                header, value = encoded.split(",", 1)
                mime = header[5:].split(";", 1)[0].lower()
                duration_match = re.search(r";duration=([0-9.]+)", header, re.I)
                if duration_match:
                    duration = float(duration_match.group(1))
            raw = base64.b64decode(value, validate=True)
            is_video = mime.startswith("video/")
            size_limit = 40 * 1024 * 1024 if is_video else max(VISION_MAX_IMAGE_BYTES, 15 * 1024 * 1024)
            if not raw or len(raw) > size_limit:
                raise ValueError(f"Attachment {index} is empty or too large")
            if is_video and (duration is None or duration <= 0 or duration > 60):
                raise ValueError(f"Video attachment {index} must include a valid duration of 60 seconds or less")
            if raw.startswith(b"\x89PNG\r\n\x1a\n"):
                extension = ".png"
            elif raw.startswith(b"\xff\xd8\xff"):
                extension = ".jpg"
            elif raw.startswith((b"GIF87a", b"GIF89a")):
                extension = ".gif"
            elif len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
                extension = ".webp"
            elif is_video and len(raw) >= 12 and raw[4:8] == b"ftyp":
                extension = ".mov" if mime == "video/quicktime" else ".mp4"
            elif is_video and raw.startswith(b"\x1aE\xdf\xa3"):
                extension = ".webm"
            else:
                extension = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}.get(mime)
                if not extension:
                    raise ValueError(f"Attachment {index} is not a supported image or short video")
            path = directory / f"{secrets.token_hex(6)}-{index}{extension}"
            path.write_bytes(raw)
            paths.append(str(path))
        return paths

    @staticmethod
    def _build_plan(client: Any, request: str, connected: list[str], attachment_paths: list[str]) -> list[str]:
        try:
            response = client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "Break the request into a short executable workflow. Return JSON only: {\"steps\":[\"...\"]}. Use 2-8 concrete outcome-focused steps. Do not include hidden reasoning."},
                    {"role": "user", "content": f"Request: {request}\nConnected tools: {', '.join(connected)}\nAttachments: {attachment_paths}"},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            payload = json.loads(response.choices[0].message.content or "{}")
            return [str(step).strip() for step in payload.get("steps", []) if str(step).strip()][:8]
        except Exception as exc:
            logger.warning("[WORK] Workflow planning preview failed: %s", exc)
            return []

    def run(
        self,
        request: str,
        history: list[dict] | None = None,
        images: list[str] | None = None,
        auto_approve_safe: bool = True,
        session_id: str | None = None,
        model_preference: str = "auto",
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        def check_cancelled() -> None:
            if cancel_check is not None and cancel_check():
                raise InterruptedError("Work task cancelled")

        check_cancelled()
        session_key = str(session_id or "default")
        resolved = self._resolve_pending_confirmation(session_key, request)
        if resolved is not None:
            return resolved
        attachment_paths = self._store_attachments(images)
        check_cancelled()
        if self._is_image_generation_request(request) and not self._is_linkedin_publish_request(request):
            try:
                path, artifact = generate_gemini_image(request, "work_image")
                check_cancelled()
                return {
                    "reply": "The Gemini image is ready.",
                    "artifacts": [artifact],
                    "activities": [
                        {"event": "route_selected", "message": "Fast path → Gemini Image", "route": "gemini_image_fast_path"},
                        {"event": "tool_completed", "message": "Gemini image generated", "tool": "generate_work_image"},
                    ],
                }
            except Exception as exc:
                logger.exception("[WORK] Gemini image generation failed")
                return {"reply": f"I could not generate the image: {exc}", "artifacts": [], "activities": [{"event": "tool_failed", "message": str(exc), "tool": "generate_work_image"}]}
        if not attachment_paths and self._is_simple_browser_navigation(request):
            fast_activities = [{
                "event": "route_selected",
                "message": "Fast path → Browser Operator",
                "route": "browser_navigation_fast_path",
            }]
            universal = self._stage_universal_browser_task(session_key, request, [], fast_activities)
            if universal is not None:
                return universal
        router = get_model_router()
        if not router.available:
            return {"reply": "Work Mode needs a Groq, Gemini, or OpenRouter API key. Add one in Settings.", "artifacts": [], "activities": []}
        client = router.client(model_preference)
        if self._is_linkedin_publish_request(request):
            fast_activities = [{
                "event": "route_selected",
                "message": "Fast path → LinkedIn plugin/browser workflow",
                "route": "linkedin_fast_path",
            }]
            revised = self._revise_pending_linkedin_post(
                session_key,
                request,
                history,
                attachment_paths,
                client,
                fast_activities,
            )
            if revised is not None:
                return revised
            generated_artifacts: list[dict[str, str]] = []
            if not attachment_paths and self._wants_generated_linkedin_image(request):
                fast_activities.append({"event": "tool_started", "message": "Generating the LinkedIn image...", "tool": "generate_image"})
                try:
                    generated_path, generated_artifact = self._generate_linkedin_image(request)
                    attachment_paths.append(generated_path)
                    generated_artifacts.append(generated_artifact)
                    fast_activities.append({"event": "tool_completed", "message": "LinkedIn image generated", "tool": "generate_image"})
                except Exception as exc:
                    logger.exception("[WORK] Fast LinkedIn image generation failed")
                    return {
                        "reply": f"I could not generate the LinkedIn image: {exc}",
                        "artifacts": [],
                        "activities": fast_activities + [{"event": "tool_failed", "message": str(exc), "tool": "generate_image"}],
                    }
            result = self._stage_linkedin_post(
                session_key,
                attachment_paths,
                request,
                history,
                client,
                fast_activities,
            )
            result["artifacts"] = generated_artifacts + list(result.get("artifacts") or [])
            return result

        tools = self.registry.llm_tools()
        connected = [p["name"] for p in self.registry.list_plugins() if p["enabled"] and p["connected"]]
        plan = self._build_plan(client, request, connected, attachment_paths)
        check_cancelled()
        planned_activities = [{"event": "workflow_planned", "message": f"Planned {len(plan)} steps", "steps": plan}] if plan else []
        revised = self._revise_pending_linkedin_post(
            session_key,
            request,
            history,
            attachment_paths,
            client,
            planned_activities,
        )
        if revised is not None:
            return revised
        universal = self._stage_universal_browser_task(session_key, request, attachment_paths, planned_activities)
        if universal is not None:
            return universal
        system = (
            "You are E.D.I.T.H. Work Mode, an execution assistant. Use the available tools to produce the requested result. "
            "Execute the supplied workflow across as many tools as needed. Never claim a file, browser, or cloud action succeeded unless a tool result says so. "
            "Chain research into document/spreadsheet/presentation tools when requested. Keep slide bullets concise. "
            "Prefer a direct connected plugin. When none exists for a website, use browser_task. "
            f"Read-only browser steps {'may run automatically' if auto_approve_safe else 'must wait for confirmation'}. "
            "For browser login, upload, publish, submit, edit, delete, purchase, or message actions, confirmed MUST be false on the initial request. Set it true only when the latest user message is a separate confirmation of the exact pending action, and pass the confirmation_id from the pending message. "
            "Never invent a confirmation ID, never interpret a confirmation ID as a filename, and never call a file tool to locate one. Do not ask for browser confirmation in prose: call browser_task with confirmed=false so Browser Operator creates the single real confirmation request and shows the prepared content. "
            "Never ask for or handle passwords, one-time codes, or payment credentials; open the site so the user can complete authentication privately. "
            "For gmail_send, confirmed may be true only when the current user message explicitly authorizes sending that exact email; otherwise request confirmation. "
            "For google_drive_upload and google_calendar_create, confirmed may be true only when the current user message explicitly authorizes that exact action; otherwise request confirmation. "
            "Google Tasks can store a due date but may not preserve a notification time, so place an explicitly requested time in notes too. "
            "Default local services, post offices, deliveries, shopping, prices, availability, and regulations to India unless the user explicitly names another country or asks for a global comparison. "
            f"Current local time: {datetime.now().astimezone().isoformat()}. Connected plugins: {', '.join(connected)}."
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for turn in (history or [])[-5:]:
            if turn.get("user"): messages.append({"role": "user", "content": str(turn["user"])})
            if turn.get("assistant"): messages.append({"role": "assistant", "content": str(turn["assistant"])})
        if plan:
            messages.append({"role": "system", "content": "Executable workflow:\n" + "\n".join(f"{index}. {step}" for index, step in enumerate(plan, 1))})
        attachment_context = f"\nE.D.I.T.H. attachment paths available to tools: {attachment_paths}" if attachment_paths else ""
        messages.append({"role": "user", "content": request + attachment_context})
        activities = planned_activities
        artifacts, browser_tasks, browser_jobs = [], [], []
        max_steps = max(1, min(int(__import__("os").getenv("MAX_TOOL_STEPS", "16")), 24))
        for step in range(max_steps):
            check_cancelled()
            kwargs = {"model": config.GROQ_MODEL, "messages": messages, "temperature": 0.2}
            if tools: kwargs.update({"tools": tools, "tool_choice": "auto"})
            response = client.chat.completions.create(**kwargs)
            check_cancelled()
            message = response.choices[0].message
            tool_calls = message.tool_calls or []
            if not tool_calls:
                actions = {}
                if browser_tasks: actions["browser_tasks"] = browser_tasks
                if browser_jobs: actions["browser_jobs"] = browser_jobs
                return {"reply": message.content or "Work completed.", "artifacts": artifacts, "activities": activities, "actions": actions}
            assistant_message = {"role": "assistant", "content": message.content or "", "tool_calls": []}
            for call in tool_calls:
                check_cancelled()
                assistant_message["tool_calls"].append({"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": call.function.arguments}})
            messages.append(assistant_message)
            for call in tool_calls:
                name = call.function.name
                try: arguments = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError: arguments = {}
                if name == "browser_task" and not auto_approve_safe:
                    arguments["force_confirmation"] = True
                activities.append({"event": "tool_started", "message": f"Running {name.replace('_', ' ')}...", "tool": name, "step": step + 1})
                result = self.registry.execute(name, arguments).as_dict()
                check_cancelled()
                artifacts.extend(result.get("artifacts") or [])
                browser_task = (result.get("data") or {}).get("browser_task") if isinstance(result.get("data"), dict) else None
                if browser_task:
                    browser_tasks.append(browser_task)
                browser_job = (result.get("data") or {}).get("browser_job") if isinstance(result.get("data"), dict) else None
                if browser_job:
                    browser_jobs.append(browser_job)
                activities.append({"event": "tool_completed" if result["success"] else "tool_failed", "message": result.get("message"), "tool": name, "step": step + 1})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False, default=str)})
                if result.get("confirmation_required"):
                    confirmation_data = result.get("data") if isinstance(result.get("data"), dict) else {}
                    confirmation_id = confirmation_data.get("confirmation_id")
                    pending_task = confirmation_data.get("pending_browser_task")
                    if name == "browser_task" and confirmation_id and pending_task:
                        self._set_pending(session_key, {"confirmation_id": confirmation_id, "task": pending_task})
                    return {"reply": result["message"], "artifacts": artifacts, "activities": activities, "confirmation": result.get("data"), "actions": {}}
        actions = {}
        if browser_tasks: actions["browser_tasks"] = browser_tasks
        if browser_jobs: actions["browser_jobs"] = browser_jobs
        return {"reply": f"I stopped after {max_steps} tool steps to prevent an infinite loop. Please narrow the task or continue from the current artifacts.", "artifacts": artifacts, "activities": activities, "actions": actions}


_service = WorkModeService()


def get_work_mode_service() -> WorkModeService:
    return _service
