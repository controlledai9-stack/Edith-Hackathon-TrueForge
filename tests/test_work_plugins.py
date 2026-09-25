import base64
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import Mock, patch

from app.plugins import google_workspace
from app.plugins import linkedin as linkedin_module
from app.plugins.base import ToolResult
from app.plugins.browser_operator import BrowserOperatorPlugin
from app.plugins.google_workspace import GmailPlugin, GoogleCalendarPlugin, GoogleDrivePlugin
from app.plugins.linkedin import LinkedInPlugin
from app.plugins.local_tools import DocumentsPlugin, FilesPlugin, NotebooksPlugin, PDFPlugin, PresentationsPlugin, SpreadsheetsPlugin
from app.plugins.marketplace import PluginMarketplace
from app.plugins.registry import PluginRegistry
from app.plugins.registry import get_plugin_registry
from app.services.work_mode_service import WorkModeService
from app.services import gemini_image_service as gemini_image_module
from app.services import work_mode_service as work_mode_module
from app.services.universal_browser_service import UniversalBrowserService
from app.services.universal_browser_worker import _linkedin_action


class PluginRegistryTests(unittest.TestCase):
    def test_registry_exposes_real_local_tools(self):
        tools = {tool.name for tool in get_plugin_registry().list_tools()}
        self.assertTrue({
            "create_document", "create_excel", "create_presentation", "create_pdf",
            "web_search", "read_url", "create_visualization", "create_site",
            "github_repository", "github_issues", "presentation_template_save",
            "browser_task",
            "create_text_file", "create_notebook",
        }.issubset(tools))

    def test_marketplace_install_registers_a_real_browser_tool_and_persists_manifest(self):
        registry = PluginRegistry()
        browser = Mock()
        browser.connected = True
        browser.stage.return_value = ToolResult(True, "browser_operator", "browser_task", message="started")
        with TemporaryDirectory() as directory, patch.object(PluginMarketplace, "_PATH", Path(directory) / "installed.json"):
            marketplace = PluginMarketplace(registry, browser)
            metadata = marketplace.install("canva")
            tool = registry.get_plugin("canva").get_tools()[0]
            result = tool.handler("Create a design", "navigate", confirmed=False)
            self.assertTrue((Path(directory) / "installed.json").is_file())
        self.assertEqual(metadata["id"], "canva")
        self.assertEqual(tool.name, "canva_browser_task")
        self.assertTrue(result.success)
        browser.stage.assert_called_once()

    def test_browser_operator_auto_approves_reads_but_confirms_publishing(self):
        with TemporaryDirectory() as directory, patch.object(BrowserOperatorPlugin, "_PENDING_PATH", Path(directory) / "pending.json"):
            operator = BrowserOperatorPlugin()
            manager = Mock()
            manager.submit.side_effect = lambda task: {"id": "job123", "status": "queued", "message": "queued"}
            with patch("app.plugins.browser_operator.validate_public_url", return_value="https://www.linkedin.com"), patch("app.services.universal_browser_service.get_universal_browser_service", return_value=manager):
                read = operator.stage("https://www.linkedin.com", "Read the company page", "read")
                publish = operator.stage("https://www.linkedin.com", "Publish the prepared post", "publish")
                confirmation_id = publish.data["confirmation_id"]
                confirmed = operator.stage("https://unused.example", "unused", "publish", True, confirmation_id=confirmation_id)

        self.assertTrue(read.success)
        self.assertTrue(publish.confirmation_required)
        self.assertTrue(confirmed.success)
        self.assertEqual(confirmed.data["browser_job"]["objective"], "Publish the prepared post")

    def test_browser_operator_can_require_confirmation_for_safe_reads(self):
        with TemporaryDirectory() as directory, patch.object(BrowserOperatorPlugin, "_PENDING_PATH", Path(directory) / "pending.json"):
            operator = BrowserOperatorPlugin()
            with patch("app.plugins.browser_operator.validate_public_url", return_value="https://example.com"):
                read = operator.stage("https://example.com", "Read the page", "read", force_confirmation=True)
            operator.cancel_pending(read.data["confirmation_id"])
        self.assertTrue(read.confirmation_required)

    def test_browser_operator_rejects_invented_confirmation_ids(self):
        with TemporaryDirectory() as directory, patch.object(BrowserOperatorPlugin, "_PENDING_PATH", Path(directory) / "pending.json"):
            operator = BrowserOperatorPlugin()
            with patch("app.plugins.browser_operator.validate_public_url", return_value="https://www.linkedin.com"):
                result = operator.stage(
                    "https://www.linkedin.com",
                    "Publish a post",
                    "publish",
                    confirmed=True,
                    confirmation_id="linkedin_post_001",
                )
        self.assertFalse(result.success)
        self.assertIn("not found", result.error)

    def test_work_mode_resolves_natural_confirmation_without_file_lookup(self):
        class FakeRegistry:
            def __init__(self):
                self.calls = []

            def execute(self, name, arguments):
                self.calls.append((name, arguments))
                return ToolResult(True, "browser_operator", name, data={"browser_task": arguments}, message="Browser task ready")

            def get_plugin(self, _plugin_id):
                return None

        with TemporaryDirectory() as directory, patch.object(WorkModeService, "_PENDING_PATH", Path(directory) / "sessions.json"):
            service = WorkModeService()
            service.registry = FakeRegistry()
            service._set_pending("session-1", {
                "confirmation_id": "a1b2c3d4",
                "task": {
                    "url": "https://www.linkedin.com/feed/",
                    "objective": "Publish the approved post",
                    "action_type": "publish",
                    "files": [{"path": "image.jpg", "name": "image.jpg"}],
                    "context": "Approved caption",
                },
            })
            result = service._resolve_pending_confirmation("session-1", "Yeah, I confirm. Post it.")

        self.assertEqual(service.registry.calls[0][0], "browser_task")
        self.assertEqual(service.registry.calls[0][1]["confirmation_id"], "a1b2c3d4")
        self.assertEqual(service.registry.calls[0][1]["file_paths"], ["image.jpg"])
        self.assertNotIn("completed", result["reply"].lower())

    def test_reddit_post_is_staged_through_universal_browser(self):
        class FakeRegistry:
            def __init__(self): self.calls = []
            def execute(self, name, arguments):
                self.calls.append((name, arguments))
                task = {"url": arguments["url"], "objective": arguments["objective"], "action_type": arguments["action_type"], "files": [], "context": arguments["context"]}
                return ToolResult(False, "browser_operator", name, data={"confirmation_id": "reddit01", "pending_browser_task": task}, message="Confirm Reddit post", confirmation_required=True)

        with TemporaryDirectory() as directory, patch.object(WorkModeService, "_PENDING_PATH", Path(directory) / "sessions.json"):
            service = WorkModeService()
            service.registry = FakeRegistry()
            result = service._stage_universal_browser_task("session-r", "Post this announcement on Reddit", [])

        name, arguments = service.registry.calls[0]
        self.assertEqual(name, "browser_task")
        self.assertEqual(arguments["url"], "https://www.reddit.com/submit")
        self.assertEqual(arguments["action_type"], "publish")
        self.assertTrue(result["confirmation"])


class UniversalBrowserServiceTests(unittest.TestCase):
    def test_linkedin_policy_opens_composer_instead_of_requesting_element_ids(self):
        task = {"url": "https://www.linkedin.com/feed/", "action_type": "publish", "context": "Approved caption", "files": [{"path": "image.jpg"}]}
        state = {"url": task["url"], "body": "Feed", "elements": [{"id": "e22", "tag": "button", "text": "Start a post", "label": ""}]}
        action = _linkedin_action(task, state, [])
        self.assertEqual(action["action"], "click")
        self.assertEqual(action["id"], "e22")

    def test_linkedin_policy_fills_caption_then_uploads_image(self):
        task = {"url": "https://www.linkedin.com/feed/", "action_type": "publish", "context": "Approved caption", "files": [{"path": "image.jpg"}]}
        editor_state = {"url": task["url"], "body": "Create a post", "elements": [{"id": "e5", "tag": "div", "label": "Text editor for creating content"}]}
        fill = _linkedin_action(task, editor_state, [])
        self.assertEqual(fill, {"action": "fill", "id": "e5", "value": "Approved caption", "_intent": "linkedin_fill_caption"})

        upload_state = {"url": task["url"], "body": "Create a post Approved caption", "elements": [
            {"id": "e5", "tag": "div", "label": "Text editor for creating content"},
            {"id": "e9", "tag": "input", "type": "file", "label": ""},
        ]}
        upload = _linkedin_action(task, upload_state, [fill])
        self.assertEqual(upload["action"], "upload")
        self.assertEqual(upload["id"], "e9")

    def test_submit_persists_job_and_starts_isolated_worker(self):
        with TemporaryDirectory() as directory:
            service = UniversalBrowserService()
            service.jobs_dir = Path(directory)
            with patch.object(service, "available", return_value=True), patch("app.services.universal_browser_service.subprocess.Popen") as process:
                job = service.submit({"url": "https://www.reddit.com/submit", "objective": "Post", "files": []})
            stored = service.get(job["id"])
        self.assertEqual(stored["status"], "queued")
        self.assertEqual(stored["task"]["url"], "https://www.reddit.com/submit")
        process.assert_called_once()

    def test_waiting_browser_job_accepts_one_sanitized_interaction(self):
        with TemporaryDirectory() as directory:
            service = UniversalBrowserService()
            service.jobs_dir = Path(directory)
            service._write({
                "id": "job123", "status": "waiting_for_auth", "message": "Sign in",
                "task": {"url": "https://example.com"}, "updated_at": 0,
            })
            queued = service.interact("job123", {"type": "click", "x": 200, "y": 350})
            stored = service.get("job123")

        self.assertEqual(queued["interactive_command"]["type"], "click")
        self.assertEqual(stored["interactive_command"]["x"], 200.0)
        self.assertEqual(stored["interactive_command"]["y"], 350.0)

    def test_completed_browser_job_rejects_interaction(self):
        with TemporaryDirectory() as directory:
            service = UniversalBrowserService()
            service.jobs_dir = Path(directory)
            service._write({
                "id": "jobdone", "status": "completed", "message": "Done",
                "task": {"url": "https://example.com"}, "updated_at": 0,
            })
            with self.assertRaisesRegex(ValueError, "no longer interactive"):
                service.interact("jobdone", {"type": "key", "key": "Enter"})

    def test_linkedin_publish_request_uses_connected_linkedin_plugin_even_if_model_would_refuse(self):
        class FakeRegistry:
            def __init__(self):
                self.calls = []

            def execute(self, name, arguments):
                self.calls.append((name, arguments))
                task = {
                    "caption": arguments["caption"],
                    "image_path": arguments["image_path"],
                }
                return ToolResult(
                    False,
                    "linkedin",
                    name,
                    data={"confirmation_id": "real1234", "pending_linkedin_post": task},
                    message="Please confirm this LinkedIn post [real1234]",
                    confirmation_required=True,
                )

            def get_plugin(self, _plugin_id):
                return type("ConnectedLinkedIn", (), {"connected": True, "enabled": True})()

        with TemporaryDirectory() as directory, patch.object(WorkModeService, "_PENDING_PATH", Path(directory) / "sessions.json"):
            service = WorkModeService()
            service.registry = FakeRegistry()
            self.assertTrue(service._is_linkedin_publish_request("Upload this image and post it on my LinkedIn"))
            result = service._stage_linkedin_post(
                "session-2",
                ["work-mode.jpg"],
                "Post this Work Mode announcement on LinkedIn",
                [],
                Mock(),
            )

        name, arguments = service.registry.calls[0]
        self.assertEqual(name, "linkedin_publish")
        self.assertEqual(arguments["image_path"], "work-mode.jpg")
        self.assertIn("PowerPoint presentations", arguments["caption"])
        self.assertTrue(result["confirmation"])

    def test_research_homework_caption_uses_research_features_not_work_plugins(self):
        service = WorkModeService()
        caption, subject = service._linkedin_caption_for_request(
            "Change it to Research/Homework mode and list its features",
            [{"user": "Post my research mode update"}],
            Mock(),
        )
        self.assertEqual(subject, "Research Mode")
        self.assertIn("solution whiteboard", caption)
        self.assertIn("Snap Queue", caption)
        self.assertIn("formula index", caption)
        self.assertNotIn("PowerPoint presentations", caption)

    def test_linkedin_router_understands_put_png_and_context_on_linkedin(self):
        request = "I provided a PNG; create Research Mode context and put both the PNG and context on my LinkedIn"
        service = WorkModeService()
        self.assertTrue(service._is_linkedin_publish_request(request))
        caption, subject = service._linkedin_caption_for_request(request, [], Mock())
        self.assertEqual(subject, "Research Mode")
        self.assertIn("Research Mode can:", caption)
        self.assertIn("Snap Queue", caption)
        self.assertNotEqual(caption, request)

    def test_youtube_navigation_uses_homepage_but_upload_requests_use_studio_route(self):
        service = WorkModeService()
        self.assertEqual("https://www.youtube.com/", service._infer_browser_destination("Open YouTube for me"))
        self.assertEqual("https://www.youtube.com/upload", service._infer_browser_destination("Upload this video to YouTube"))

    def test_simple_youtube_navigation_skips_model_planning(self):
        class FakeRegistry:
            def execute(self, name, arguments):
                self.name = name
                self.arguments = arguments
                return ToolResult(
                    True,
                    "browser_operator",
                    name,
                    data={"browser_job": {"id": "youtube-fast", "status": "queued", **arguments}},
                    message="Universal Browser started: Open YouTube for me",
                )

        with TemporaryDirectory() as directory, patch.object(WorkModeService, "_PENDING_PATH", Path(directory) / "sessions.json"):
            service = WorkModeService()
            service.registry = FakeRegistry()
            with patch.object(service, "_build_plan") as build_plan:
                result = service.run("Open YouTube for me", session_id="youtube-session")

        build_plan.assert_not_called()
        self.assertEqual(service.registry.name, "browser_task")
        self.assertEqual(service.registry.arguments["url"], "https://www.youtube.com/")
        self.assertEqual(service.registry.arguments["action_type"], "navigate")
        self.assertEqual(result["activities"][0]["route"], "browser_navigation_fast_path")

    def test_linkedin_fast_path_can_generate_local_image_without_browser_image_creator(self):
        image_bytes = b"\x89PNG\r\n\x1a\nfast-image"
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "image/png", "data": base64.b64encode(image_bytes).decode("ascii")
        }}]}}]}
        with (
            TemporaryDirectory() as directory,
            patch.object(gemini_image_module, "artifact_path", return_value=Path(directory) / "linkedin_generated.png"),
            patch.object(gemini_image_module.config, "GEMINI_API_KEY", "test-gemini-key"),
            patch.object(gemini_image_module.config, "GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"),
            patch.object(gemini_image_module.requests, "post", return_value=response) as post,
        ):
            service = WorkModeService()
            path, artifact = service._generate_linkedin_image(
                "Generate an image on modern AI development and rapid growth, then post it to LinkedIn"
            )
            stored = Path(path)
            self.assertTrue(stored.is_file())
            self.assertEqual(image_bytes, stored.read_bytes())
            self.assertEqual("image/png", artifact["mime_type"])
            self.assertIn("gemini-3.1-flash-image:generateContent", post.call_args.args[0])
            self.assertEqual("test-gemini-key", post.call_args.kwargs["headers"]["x-goog-api-key"])
            self.assertEqual(["TEXT", "IMAGE"], post.call_args.kwargs["json"]["generationConfig"]["responseModalities"])

    def test_linkedin_run_skips_general_planning_and_stages_one_direct_post(self):
        staged = {
            "reply": "Confirm the LinkedIn post",
            "artifacts": [],
            "activities": [],
            "confirmation": {"confirmation_id": "fast123"},
            "actions": {},
        }
        generated = ("C:/generated.png", {"name": "generated.png", "path": "C:/generated.png", "mime_type": "image/png"})
        with (
            TemporaryDirectory() as directory,
            patch.object(WorkModeService, "_PENDING_PATH", Path(directory) / "pending.json"),
            patch.object(work_mode_module.config, "GROQ_API_KEYS", ["test-key"]),
        ):
            service = WorkModeService()
            with (
                patch.object(service, "_build_plan", side_effect=AssertionError("general planner should not run")),
                patch.object(service, "_generate_linkedin_image", return_value=generated) as generate,
                patch.object(service, "_stage_linkedin_post", return_value=staged) as stage,
            ):
                result = service.run(
                    "Generate an image about rapid AI growth and post it on LinkedIn",
                    session_id="fast-session",
                )
        generate.assert_called_once()
        stage.assert_called_once()
        self.assertEqual("fast123", result["confirmation"]["confirmation_id"])
        self.assertEqual("generated.png", result["artifacts"][0]["name"])

    def test_linkedin_media_only_request_does_not_invent_a_caption(self):
        service = WorkModeService()
        caption, subject = service._linkedin_caption_for_request(
            "Post only these three images on my LinkedIn without a caption", [], Mock()
        )
        self.assertEqual(caption, "")
        self.assertEqual(subject, "media-only")

    def test_linkedin_revision_preserves_image_and_replaces_old_pending_action(self):
        class CancelPlugin:
            def __init__(self): self.cancelled = []
            def cancel_pending(self, confirmation_id): self.cancelled.append(confirmation_id)

        class FakeRegistry:
            def __init__(self):
                self.calls = []
                self.browser = CancelPlugin()
                self.linkedin = type("DisconnectedLinkedIn", (), {"connected": False, "enabled": True})()
            def get_plugin(self, plugin_id):
                return self.browser if plugin_id == "browser_operator" else self.linkedin
            def execute(self, name, arguments):
                self.calls.append((name, arguments))
                task = {
                    "url": arguments["url"], "objective": arguments["objective"],
                    "action_type": arguments["action_type"], "context": arguments["context"],
                    "files": [{"path": path, "name": Path(path).name} for path in arguments["file_paths"]],
                }
                return ToolResult(False, "browser_operator", name, data={"confirmation_id": "newdraft1", "pending_browser_task": task}, message="Confirm revised post", confirmation_required=True)

        with TemporaryDirectory() as directory, patch.object(WorkModeService, "_PENDING_PATH", Path(directory) / "sessions.json"):
            service = WorkModeService()
            service.registry = FakeRegistry()
            service._set_pending("session-r", {
                "tool_name": "browser_task", "confirmation_id": "olddraft1",
                "task": {"url": "https://www.linkedin.com/feed/", "objective": "Old Work post", "action_type": "publish", "context": "Old caption", "files": [{"path": "research.png", "name": "research.png"}]},
            })
            result = service._revise_pending_linkedin_post(
                "session-r", "No, change the context to Research/Homework mode and keep the image", [], [], Mock(), []
            )

        self.assertEqual(service.registry.browser.cancelled, ["olddraft1"])
        self.assertEqual(service.registry.calls[0][1]["file_paths"], ["research.png"])
        self.assertIn("solution whiteboard", service.registry.calls[0][1]["context"])
        self.assertEqual(result["confirmation"]["confirmation_id"], "newdraft1")

    def test_attachment_storage_preserves_png_extension(self):
        raw = b"\x89PNG\r\n\x1a\n" + b"test-png-content"
        encoded = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
        with TemporaryDirectory() as directory, patch.object(work_mode_module, "DATA_DIR", Path(directory)):
            paths = WorkModeService._store_attachments([encoded])
            stored = Path(paths[0])
            self.assertEqual(stored.suffix, ".png")
            self.assertEqual(stored.read_bytes(), raw)

    def test_attachment_storage_accepts_short_mp4_and_rejects_long_video(self):
        raw = b"\x00\x00\x00\x18ftypmp42" + b"short-video"
        payload = base64.b64encode(raw).decode("ascii")
        short = "data:video/mp4;duration=59.5;base64," + payload
        long = "data:video/mp4;duration=60.1;base64," + payload
        with TemporaryDirectory() as directory, patch.object(work_mode_module, "DATA_DIR", Path(directory)):
            paths = WorkModeService._store_attachments([short])
            self.assertEqual(Path(paths[0]).suffix, ".mp4")
            with self.assertRaisesRegex(ValueError, "60 seconds or less"):
                WorkModeService._store_attachments([long])

    def test_attachment_storage_limits_work_tasks_to_five_files(self):
        raw = b"\x89PNG\r\n\x1a\n" + b"content"
        encoded = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
        with self.assertRaisesRegex(ValueError, "up to five"):
            WorkModeService._store_attachments([encoded] * 6)

    def test_multiple_linkedin_attachments_use_browser_and_keep_every_path(self):
        class FakeRegistry:
            def __init__(self): self.calls = []
            def get_plugin(self, _plugin_id):
                return type("ConnectedLinkedIn", (), {"connected": True, "enabled": True})()
            def execute(self, name, arguments):
                self.calls.append((name, arguments))
                task = {"url": arguments["url"], "files": [{"path": path} for path in arguments["file_paths"]]}
                return ToolResult(False, "browser_operator", name, data={"confirmation_id": "multi123", "pending_browser_task": task}, message="Confirm", confirmation_required=True)

        with TemporaryDirectory() as directory, patch.object(WorkModeService, "_PENDING_PATH", Path(directory) / "sessions.json"):
            service = WorkModeService()
            service.registry = FakeRegistry()
            service._stage_linkedin_post("multi", ["one.png", "two.jpg", "three.mp4"], "Post my Research Mode update", [], Mock())
        name, arguments = service.registry.calls[0]
        self.assertEqual(name, "browser_task")
        self.assertEqual(arguments["file_paths"], ["one.png", "two.jpg", "three.mp4"])
        self.assertIn("Research", arguments["context"])

    def test_gmail_send_requires_exact_confirmation_before_api_call(self):
        result = GmailPlugin().send("person@example.com", "Test", "Hello", confirmed=False)
        self.assertFalse(result.success)
        self.assertTrue(result.confirmation_required)

    def test_google_cloud_writes_require_confirmation(self):
        drive = GoogleDrivePlugin().upload("example.pptx", confirmed=False)
        calendar = GoogleCalendarPlugin().create_event("Review", "2026-08-24T10:00:00+05:30", "2026-08-24T10:30:00+05:30", confirmed=False)
        self.assertTrue(drive.confirmation_required)
        self.assertTrue(calendar.confirmation_required)


class GoogleOAuthStateTests(unittest.TestCase):
    def test_state_survives_process_memory_loss_and_is_single_use(self):
        with TemporaryDirectory() as directory, patch.object(google_workspace, "OAUTH_STATE_DIR", Path(directory)):
            google_workspace._store_oauth_state("state-123")
            self.assertTrue(google_workspace._consume_oauth_state("state-123"))
            self.assertFalse(google_workspace._consume_oauth_state("state-123"))

    def test_expired_state_is_rejected(self):
        with TemporaryDirectory() as directory, patch.object(google_workspace, "OAUTH_STATE_DIR", Path(directory)):
            with patch.object(google_workspace.time, "time", return_value=1000):
                google_workspace._store_oauth_state("expired-state")
            with patch.object(google_workspace.time, "time", return_value=1000 + google_workspace.OAUTH_STATE_TTL_SECONDS + 1):
                self.assertFalse(google_workspace._consume_oauth_state("expired-state"))

    def test_pkce_verifier_is_persisted_and_restored_for_token_exchange(self):
        fake_flow = Mock()
        fake_flow.credentials.to_json.return_value = '{"token":"saved"}'
        with TemporaryDirectory() as directory, \
             patch.object(google_workspace, "OAUTH_STATE_DIR", Path(directory) / "states"), \
             patch.object(google_workspace, "TOKEN_PATH", Path(directory) / "google_token.json"), \
             patch("google_auth_oauthlib.flow.Flow.from_client_config", return_value=fake_flow) as from_config:
            google_workspace._store_oauth_state("pkce-state", "saved-code-verifier")
            google_workspace.finish_authorization("pkce-state", "authorization-code")

        self.assertEqual(from_config.call_args.kwargs["code_verifier"], "saved-code-verifier")
        self.assertFalse(from_config.call_args.kwargs["autogenerate_code_verifier"])
        fake_flow.fetch_token.assert_called_once_with(code="authorization-code")

    def test_expired_google_token_with_refresh_token_remains_connected_without_network(self):
        fake_credentials = Mock(valid=False, expired=True, refresh_token="refresh-token")
        with TemporaryDirectory() as directory:
            token_path = Path(directory) / "google_token.json"
            token_path.write_text("{}", encoding="utf-8")
            with (
                patch.object(google_workspace, "TOKEN_PATH", token_path),
                patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=fake_credentials),
            ):
                self.assertTrue(GmailPlugin().connected)


class LinkedInPluginTests(unittest.TestCase):
    def test_confirmed_image_post_uses_official_image_and_posts_apis(self):
        from config import DATA_DIR
        with TemporaryDirectory(dir=DATA_DIR) as directory:
            root = Path(directory)
            image = root / "announcement.jpg"
            image.write_bytes(b"jpeg-test")
            initialized = Mock()
            initialized.json.return_value = {"value": {"uploadUrl": "https://upload.linkedin.test/image", "image": "urn:li:image:123"}}
            initialized.raise_for_status.return_value = None
            posted = Mock(headers={"x-restli-id": "urn:li:share:456"})
            posted.raise_for_status.return_value = None
            uploaded = Mock()
            uploaded.raise_for_status.return_value = None
            with (
                patch.object(linkedin_module, "PENDING_PATH", root / "pending.json"),
                patch.object(linkedin_module, "_token", return_value={"access_token": "token", "author": "urn:li:person:abc"}),
                patch.object(linkedin_module.requests, "post", side_effect=[initialized, posted]) as post,
                patch.object(linkedin_module.requests, "put", return_value=uploaded) as put,
            ):
                plugin = LinkedInPlugin()
                staged = plugin.publish("Approved caption", str(image), confirmed=False)
                result = plugin.publish("unused", str(image), confirmed=True, confirmation_id=staged.data["confirmation_id"])

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["post_id"], "urn:li:share:456")
        self.assertIn("initializeUpload", post.call_args_list[0].args[0])
        self.assertEqual(put.call_args.args[0], "https://upload.linkedin.test/image")
        self.assertTrue(post.call_args_list[1].args[0].endswith("/rest/posts"))


class ArtifactGenerationTests(unittest.TestCase):
    def test_notepad_and_notebook_generation(self):
        notes = FilesPlugin().create_text_file("Useful context", "context.txt")
        notebook = NotebooksPlugin().create_notebook([
            {"type": "markdown", "content": "# Analysis"},
            {"type": "code", "content": "print('ready')"},
        ], "analysis.ipynb")
        self.assertTrue(notes.success, notes.error)
        self.assertTrue(notebook.success, notebook.error)
        self.assertTrue(Path(notes.artifacts[0].path).is_file())
        self.assertTrue(Path(notebook.artifacts[0].path).is_file())

    def test_excel_generation(self):
        result = SpreadsheetsPlugin().create_excel(["Name", "Score"], [["Asha", 91], ["Leo", 88]], "plugin_test.xlsx")
        self.assertTrue(result.success, result.error)
        self.assertTrue(Path(result.artifacts[0].path).is_file())

    def test_word_generation(self):
        result = DocumentsPlugin().create_document("Test Report", [{"heading": "Summary", "paragraphs": ["A generated report."]}], "plugin_test.docx")
        self.assertTrue(result.success, result.error)
        self.assertTrue(Path(result.artifacts[0].path).is_file())

    def test_trueforge_content_alias_is_written_to_pdf_and_word(self):
        sections = [{"title": "Pokémon Summary", "content": "1. First summary line.\n2. Second summary line."}]
        pdf = PDFPlugin().create_pdf("Pokémon Summary", sections, "alias_content_test.pdf")
        word = DocumentsPlugin().create_document("Pokémon Summary", sections, "alias_content_test.docx")
        self.assertTrue(pdf.success, pdf.error)
        self.assertTrue(word.success, word.error)

        import fitz
        from docx import Document
        with fitz.open(pdf.artifacts[0].path) as document:
            pdf_text = "\n".join(page.get_text() for page in document)
        word_text = "\n".join(paragraph.text for paragraph in Document(word.artifacts[0].path).paragraphs)
        for expected in ("First summary line", "Second summary line"):
            self.assertIn(expected, pdf_text)
            self.assertIn(expected, word_text)

    def test_one_page_pdf_option_keeps_a_dense_report_on_one_page(self):
        sections = [
            {"title": f"Section {index}", "content": "- Synthetic metric: 65% complete\n- Status: On track\n- Owner: Demo Team"}
            for index in range(1, 8)
        ]
        result = PDFPlugin().create_pdf("Synthetic Project Report", sections, "one_page_plugin_test.pdf", one_page=True)
        self.assertTrue(result.success, result.error)

        import fitz
        with fitz.open(result.artifacts[0].path) as document:
            self.assertEqual(document.page_count, 1)
            text = document[0].get_text()
        self.assertIn("Synthetic Project Report", text)
        self.assertIn("Section 7", text)

    def test_powerpoint_generation(self):
        result = PresentationsPlugin().create_presentation("AI", [{"title": "Overview", "bullets": ["One", "Two"]}], "plugin_test.pptx")
        self.assertTrue(result.success, result.error)
        self.assertTrue(Path(result.artifacts[0].path).is_file())


if __name__ == "__main__":
    unittest.main()
