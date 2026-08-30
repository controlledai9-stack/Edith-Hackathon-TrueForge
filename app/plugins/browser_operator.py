from __future__ import annotations

import json
import secrets
from threading import RLock
from typing import Any

from config import DATA_DIR
from app.plugins.base import Plugin, ToolDefinition, ToolResult
from app.plugins.utils import approved_path, validate_public_url


def _object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


class BrowserOperatorPlugin(Plugin):
    """Stages universal website work for E.D.I.T.H.'s dedicated browser window.

    Read-only navigation can proceed immediately. External writes and account
    actions always stop for a separate confirmation before a browser task is
    emitted to the frontend.
    """

    id, name = "browser_operator", "Browser Operator"
    description = "Run confirmed cross-site workflows in a persistent browser window, with private authentication handoff."
    permissions = [
        "open public websites",
        "reuse a user-signed-in browser session",
        "stage uploads and publishing only after confirmation",
    ]
    _WRITE_ACTIONS = {"login", "upload", "publish", "submit", "edit", "delete", "purchase", "message"}
    _PENDING_PATH = DATA_DIR / "work_mode" / "pending_browser_tasks.json"

    def __init__(self) -> None:
        super().__init__()
        self._pending_lock = RLock()
        self._pending: dict[str, dict[str, Any]] = self._load_pending()

    @property
    def connected(self) -> bool:
        from app.services.universal_browser_service import get_universal_browser_service
        return get_universal_browser_service().available()

    def _load_pending(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self._PENDING_PATH.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save_pending(self) -> None:
        self._PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._PENDING_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._pending, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self._PENDING_PATH)

    def cancel_pending(self, confirmation_id: str) -> None:
        with self._pending_lock:
            if self._pending.pop(str(confirmation_id), None) is not None:
                self._save_pending()

    def get_tools(self) -> list[ToolDefinition]:
        return [ToolDefinition(
            "browser_task",
            "Stage a browser task when no direct plugin can complete a website step. Read/navigate may run automatically. Login, upload, publish, submit, edit, delete, purchase, and message require a separate confirmation turn.",
            _object({
                "url": {"type": "string", "description": "Exact public HTTPS destination."},
                "objective": {"type": "string", "description": "Concrete outcome to carry into the browser."},
                "action_type": {"type": "string", "enum": ["read", "navigate", "login", "upload", "publish", "submit", "edit", "delete", "purchase", "message"]},
                "file_paths": {"type": "array", "items": {"type": "string"}, "description": "Optional E.D.I.T.H. attachment or artifact paths."},
                "context": {"type": "string", "description": "Prepared text, caption, or structured context for the website task."},
                "confirmed": {"type": "boolean", "description": "True only after the user separately confirms this exact external action."},
                "confirmation_id": {"type": "string", "description": "Pending action ID from E.D.I.T.H.'s confirmation message."},
            }, ["url", "objective", "action_type", "confirmed"]),
            self.stage,
            requires_confirmation=True,
        )]

    def stage(
        self,
        url: str,
        objective: str,
        action_type: str,
        confirmed: bool = False,
        file_paths: list[str] | None = None,
        context: str = "",
        confirmation_id: str = "",
        force_confirmation: bool = False,
    ) -> ToolResult:
        try:
            if confirmed and confirmation_id:
                with self._pending_lock:
                    pending = self._pending.get(str(confirmation_id))
                if pending:
                    url = pending["url"]
                    objective = pending["objective"]
                    action_type = pending["action_type"]
                    file_paths = [item["path"] for item in pending.get("files", [])]
                    context = pending.get("context", "")
                else:
                    raise ValueError("Pending browser action was not found or has expired")
            validate_public_url(url)
            action = str(action_type or "navigate").lower()
            if action not in {"read", "navigate", *self._WRITE_ACTIONS}:
                raise ValueError("Unsupported browser action")
            files = []
            for value in file_paths or []:
                source = approved_path(value)
                files.append({"name": source.name, "path": str(source)})
            task = {
                "url": url,
                "objective": str(objective).strip(),
                "action_type": action,
                "context": str(context or "")[:20_000],
                "files": files,
                "requires_login_handoff": action == "login",
            }
            if action in self._WRITE_ACTIONS and confirmed and not confirmation_id:
                raise ValueError("A real pending-action ID is required for confirmed browser changes")
            if (action in self._WRITE_ACTIONS or force_confirmation) and not confirmed:
                confirmation_id = secrets.token_hex(4)
                with self._pending_lock:
                    self._pending[confirmation_id] = task
                    self._save_pending()
                summary = f"{action} on {url}"
                if files:
                    summary += f" using {', '.join(item['name'] for item in files)}"
                return ToolResult(
                    False,
                    self.id,
                    "browser_task",
                    data={"pending_browser_task": task, "confirmation_id": confirmation_id},
                    message=(
                        f"Please confirm this exact browser action [{confirmation_id}]: {summary}."
                        + (f"\n\nPrepared content:\n{task['context']}" if task["context"] else "")
                    ),
                    confirmation_required=True,
                )
            if action == "navigate":
                return ToolResult(
                    True,
                    self.id,
                    "browser_task",
                    data={"browser_task": {**task, "open_immediately": True}},
                    message=f"Opening {task['objective']}",
                )
            from app.services.universal_browser_service import get_universal_browser_service
            job = get_universal_browser_service().submit(task)
            if confirmed and confirmation_id:
                with self._pending_lock:
                    self._pending.pop(str(confirmation_id), None)
                    self._save_pending()
            return ToolResult(
                True,
                self.id,
                "browser_task",
                data={"browser_job": {"id": job["id"], "status": job["status"], "message": job["message"], "objective": task["objective"], "url": task["url"]}},
                message=f"Browser window started: {task['objective']}",
            )
        except Exception as exc:
            return ToolResult(False, self.id, "browser_task", error=str(exc), message="Browser task could not be prepared")
