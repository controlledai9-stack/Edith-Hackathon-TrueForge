from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from threading import RLock
from typing import Any

from config import BASE_DIR, DATA_DIR


class UniversalBrowserService:
    """Persistent, file-backed browser jobs executed in isolated processes."""

    def __init__(self) -> None:
        self.jobs_dir = DATA_DIR / "browser_jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    @staticmethod
    def runtime_python() -> Path:
        configured = os.getenv("UNIVERSAL_BROWSER_PYTHON", "").strip()
        bundled = BASE_DIR / ".test-venv" / "Scripts" / "python.exe"
        if configured and Path(configured).is_file():
            return Path(configured)
        return bundled if bundled.is_file() else Path(sys.executable)

    @classmethod
    def available(cls) -> bool:
        runtime = cls.runtime_python().resolve()
        if runtime == Path(sys.executable).resolve():
            return importlib.util.find_spec("playwright") is not None
        package = runtime.parent.parent / "Lib" / "site-packages" / "playwright"
        return package.is_dir()

    def _path(self, job_id: str) -> Path:
        safe = "".join(ch for ch in str(job_id) if ch.isalnum() or ch in "-_")
        if not safe:
            raise ValueError("Invalid browser job ID")
        return self.jobs_dir / f"{safe}.json"

    def screenshot_path(self, job_id: str) -> Path:
        return self._path(job_id).with_suffix(".jpg")

    def _write(self, payload: dict[str, Any]) -> None:
        path = self._path(payload["id"])
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def submit(self, task: dict[str, Any]) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError("Universal Browser requires the Playwright runtime")
        job_id = uuid.uuid4().hex[:12]
        now = time.time()
        payload = {
            "id": job_id,
            "status": "queued",
            "message": "Universal Browser queued",
            "task": task,
            "created_at": now,
            "updated_at": now,
            "current_url": task.get("url", ""),
            "result": None,
            "error": None,
        }
        with self._lock:
            self._write(payload)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        subprocess.Popen(
            [str(self.runtime_python()), "-m", "app.services.universal_browser_worker", job_id],
            cwd=str(BASE_DIR),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=os.name != "nt",
        )
        return self.get(job_id) or payload

    def get(self, job_id: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(self._path(job_id).read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else None
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            payload = self.get(job_id)
            if not payload:
                return None
            if payload.get("status") not in {"completed", "failed", "cancelled"}:
                payload["status"] = "cancelled"
                payload["message"] = "Browser job cancelled"
                payload["updated_at"] = time.time()
                self._write(payload)
            return payload

    def interact(self, job_id: str, command: dict[str, Any]) -> dict[str, Any] | None:
        """Queue one local user interaction for a live in-chat browser job."""
        allowed = {"click", "type", "key", "scroll"}
        kind = str(command.get("type") or "").strip().lower()
        if kind not in allowed:
            raise ValueError("Unsupported browser interaction")
        with self._lock:
            payload = self.get(job_id)
            if not payload:
                return None
            if payload.get("status") not in {"waiting_for_auth", "waiting_for_user", "running"}:
                raise ValueError("This browser job is no longer interactive")
            if payload.get("interactive_command"):
                raise RuntimeError("The previous browser interaction is still being applied")
            sanitized: dict[str, Any] = {
                "id": uuid.uuid4().hex,
                "type": kind,
                "requested_at": time.time(),
            }
            if kind == "click":
                sanitized["x"] = max(0.0, min(float(command.get("x", 0)), 5000.0))
                sanitized["y"] = max(0.0, min(float(command.get("y", 0)), 5000.0))
            elif kind == "type":
                sanitized["text"] = str(command.get("text") or "")[:2000]
            elif kind == "key":
                key = str(command.get("key") or "")
                if key not in {"Enter", "Tab", "Backspace", "Escape", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"}:
                    raise ValueError("Unsupported browser key")
                sanitized["key"] = key
            else:
                sanitized["delta_y"] = max(-3000, min(int(command.get("delta_y", 0)), 3000))
            payload["interactive_command"] = sanitized
            payload["message"] = "Applying your browser interaction"
            payload["updated_at"] = time.time()
            self._write(payload)
            return payload


_service = UniversalBrowserService()


def get_universal_browser_service() -> UniversalBrowserService:
    return _service
