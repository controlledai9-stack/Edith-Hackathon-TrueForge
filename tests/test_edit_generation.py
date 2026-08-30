import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import requests

from app.services.brain_service import BrainService
from app.services.task_manager import TaskManager


class EditGenerationRoutingTests(unittest.TestCase):
    def setUp(self):
        self.brain = BrainService(groq_service=object())

    def test_generate_summary_is_content_not_browser_navigation(self):
        request = "Generate me context for a research paper on how modern AI is changing so fast"

        category, method, _elapsed = self.brain.classify_primary(request, [])
        tasks, task_method, _task_elapsed = self.brain.classify_task(request, [])
        intents = self.brain.extract_task_payloads(request, tasks, [])

        self.assertEqual("task", category)
        self.assertEqual("generation-rule", method)
        self.assertEqual(["content"], tasks)
        self.assertEqual("generation-rule", task_method)
        self.assertEqual("content", intents[0][0])
        self.assertFalse(any(intent == "open" for intent, _payload in intents))

    def test_image_revision_uses_previous_image_context(self):
        history = [
            ("Generate an image of a modern AI laboratory", "I’m generating the image now."),
        ]

        category, _method, _elapsed = self.brain.classify_primary(
            "Change the lighting to blue and keep everything else", history
        )
        tasks, _task_method, _task_elapsed = self.brain.classify_task(
            "Change the lighting to blue and keep everything else", history
        )

        self.assertEqual("task", category)
        self.assertEqual(["generate_image"], tasks)
        self.assertTrue(self.brain._last_task_decisions[0][1].startswith("Edit the previous image:"))

    def test_unparseable_task_output_does_not_default_to_google(self):
        self.assertEqual([], self.brain._parse_task_decisions("I cannot classify this"))


class EditImageArtifactTests(unittest.TestCase):
    @staticmethod
    def _wait(manager: TaskManager, task_id: str) -> dict:
        for _ in range(100):
            task = manager.get(task_id)
            if task and task["status"] in {"completed", "failed"}:
                return task
            time.sleep(0.01)
        raise AssertionError("Background image task did not finish")

    def test_generated_image_is_local_and_revision_reuses_real_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "generated.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\nverified-image-data")
            artifact = {"name": image.name, "path": str(image), "mime_type": "image/png"}
            manager = TaskManager(max_workers=1, state_path=root / "state" / "last_images.json")
            try:
                with patch("app.services.task_manager.generate_gemini_image", return_value=(str(image), artifact)) as generate:
                    first_id = manager.submit(
                        "generate image", "A modern AI laboratory", session_id="edit-session"
                    )
                    first = self._wait(manager, first_id)
                    self.assertEqual("completed", first["status"])
                    self.assertEqual("/artifacts/generated.png/preview", first["result"]["url"])
                    self.assertEqual("/artifacts/generated.png", first["result"]["download_url"])
                    self.assertFalse(first["result"]["edited_previous_image"])

                    second_id = manager.submit(
                        "generate image",
                        "Change the lighting to blue",
                        session_id="edit-session",
                        use_previous_image=True,
                    )
                    second = self._wait(manager, second_id)
                    self.assertEqual("completed", second["status"])
                    self.assertTrue(second["result"]["edited_previous_image"])
                    self.assertEqual(str(image), generate.call_args_list[1].kwargs["reference_image_path"])
            finally:
                manager._pool.shutdown(wait=True)

    def test_gemini_429_uses_verified_new_image_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "fallback.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\nverified-fallback-data")
            artifact = {"name": image.name, "path": str(image), "mime_type": "image/png"}
            manager = TaskManager(max_workers=1, state_path=root / "state.json")
            response = requests.Response()
            response.status_code = 429
            error = requests.HTTPError("429 Client Error: Too Many Requests", response=response)
            try:
                with (
                    patch("app.services.task_manager.generate_gemini_image", side_effect=error),
                    patch("app.services.task_manager.generate_verified_fallback_image", return_value=(str(image), artifact)) as fallback,
                ):
                    task_id = manager.submit("generate image", "A premium car studio logo", session_id="image-session")
                    task = self._wait(manager, task_id)
                self.assertEqual("completed", task["status"])
                self.assertEqual("fallback", task["result"]["provider"])
                fallback.assert_called_once_with("A premium car studio logo")
            finally:
                manager._pool.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
