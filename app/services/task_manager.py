import logging
import json
import threading
import time
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Any

from config import DATA_DIR
from app.services.gemini_image_service import generate_gemini_image, generate_verified_fallback_image
from app.services.task_executor import generate_content_text

logger = logging.getLogger("J.A.R.V.I.S")


class TaskManager:
    """Simple in-memory background job queue. Jobs are executed on a
    thread pool (network-bound work: image URL build + a Groq call for
    content), and their status/result is polled by the frontend via
    GET /tasks/{task_id}."""

    def __init__(self, max_workers: int = 4, state_path: Path | None = None):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        self._state_path = state_path or (DATA_DIR / "task_state" / "last_images.json")
        self._last_images: Dict[str, str] = self._load_last_images()

    def _load_last_images(self) -> Dict[str, str]:
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {}
            return {
                str(session_id): str(path)
                for session_id, path in payload.items()
                if str(session_id).strip() and Path(str(path)).is_file()
            }
        except (OSError, ValueError, TypeError):
            return {}

    def _remember_image(self, session_id: str, path: str) -> None:
        if not session_id:
            return
        with self._lock:
            self._last_images[session_id] = path
            snapshot = dict(self._last_images)
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._state_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
            temporary.replace(self._state_path)
        except OSError as exc:
            logger.warning("[TASK] Could not persist the last image reference: %s", exc)

    def submit(
        self,
        job_type: str,
        prompt: str,
        label: str = "",
        session_id: str = "",
        use_previous_image: bool = False,
    ) -> str:
        task_id = uuid.uuid4().hex[:12]
        with self._lock:
            reference_image = self._last_images.get(session_id) if use_previous_image else None
            self._tasks[task_id] = {
                "status": "pending",
                "type": job_type,
                "prompt": prompt,
                "label": label or prompt[:60],
                "result": None,
                "error": None,
                "created": time.time(),
                "session_id": session_id,
                "uses_previous_image": bool(reference_image),
            }
        self._pool.submit(self._run, task_id, job_type, prompt, session_id, reference_image)
        return task_id

    def _run(
        self,
        task_id: str,
        job_type: str,
        prompt: str,
        session_id: str = "",
        reference_image: str | None = None,
    ):
        try:
            if job_type == "generate image":
                image_prompt = prompt
                image_provider = "gemini"
                if reference_image:
                    image_prompt = (
                        "Edit the supplied previous image according to this request. Preserve all elements "
                        f"that the request does not ask to change. Request: {prompt}"
                    )
                try:
                    path, artifact = generate_gemini_image(
                        image_prompt,
                        "edith_image_edit" if reference_image else "edith_image",
                        reference_image_path=reference_image,
                    )
                except Exception as image_error:
                    status = getattr(getattr(image_error, "response", None), "status_code", None)
                    rate_limited = status == 429 or "429" in str(image_error) or "quota" in str(image_error).lower()
                    if reference_image or not rate_limited:
                        raise
                    logger.warning("[TASK] Gemini image quota reached; using verified fallback provider")
                    path, artifact = generate_verified_fallback_image(prompt)
                    image_provider = "fallback"
                encoded_name = urllib.parse.quote(artifact["name"])
                result = {
                    "type": "image",
                    "url": f"/artifacts/{encoded_name}/preview",
                    "download_url": f"/artifacts/{encoded_name}",
                    "prompt": prompt,
                    "artifact": artifact,
                    "edited_previous_image": bool(reference_image),
                    "provider": image_provider,
                }
                self._remember_image(session_id, path)
            elif job_type == "content":
                text = generate_content_text(prompt)
                result = {"type": "content", "text": text, "prompt": prompt}
            else:
                raise ValueError(f"Unknown background job type: {job_type}")

            with self._lock:
                self._tasks[task_id]["status"] = "completed"
                self._tasks[task_id]["result"] = result

        except Exception as e:
            logger.error("[TASK] Job %s (%s) failed: %s", task_id, job_type, e)
            with self._lock:
                self._tasks[task_id]["status"] = "failed"
                self._tasks[task_id]["error"] = str(e)

    def get(self, task_id: str) -> Dict[str, Any]:
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None


_task_manager_singleton = None


def get_task_manager() -> TaskManager:
    global _task_manager_singleton
    if _task_manager_singleton is None:
        _task_manager_singleton = TaskManager()
    return _task_manager_singleton
