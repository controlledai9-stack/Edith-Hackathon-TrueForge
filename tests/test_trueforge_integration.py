import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.integrations.trueforge.profiles import build_manifest
from app.integrations.trueforge.session_manager import TrueForgeSessionManager
from app.integrations.trueforge.types import HarnessEvent, SessionBinding
from app.services.trueforge_service import TrueForgeService
from config import TRUEFORGE_CODE_SANDBOX_ENABLED


class FakeClient:
    def __init__(self):
        self.created = []
        self.cancelled = []

    async def create_session(self, agent_name):
        self.created.append(agent_name)
        return {"id": "sess-test"}

    async def cancel(self, session_id):
        self.cancelled.append(session_id)
        return {"cancelled": True}


class RateLimitedClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.inputs = []

    async def get_turn(self, session_id, turn_id):
        return {"state": {"status": "error", "message": "429 rate limit"}}

    async def stream_turn(self, session_id, input_items=None, previous_turn_id="auto"):
        self.inputs.append(input_items)
        yield HarnessEvent("turn.done", {"type": "turn.done", "state": {"status": "completed"}}, 10, "main")


class SessionMappingTests(unittest.IsolatedAsyncioTestCase):
    async def test_mapping_is_persisted_and_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sessions.json"
            client = FakeClient()
            manager = TrueForgeSessionManager(client, path)
            first = await manager.get_or_create("chat-1", "research")
            second = await manager.get_or_create("chat-1", "research")
            self.assertEqual("sess-test", first.harness_session_id)
            self.assertEqual(first.harness_session_id, second.harness_session_id)
            self.assertEqual(1, len(client.created))
            self.assertIn("chat-1:research", json.loads(path.read_text(encoding="utf-8")))

    async def test_event_checkpoint_tracks_turn_sequence_and_required_actions(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = TrueForgeSessionManager(FakeClient(), Path(temporary) / "sessions.json")
            binding = SessionBinding("chat-1", "work", "sess-test")
            manager.record_event(binding, {"type": "turn.created", "turn_id": "turn-1", "id": "evt-1"}, 4)
            manager.record_event(binding, {"type": "turn.done", "id": "evt-2", "state": {"required_actions": [{"type": "approval"}]}}, 9)
            restored = manager.get("chat-1", "work")
            self.assertEqual("turn-1", restored.active_turn_id)
            self.assertEqual(9, restored.last_sequence)
            self.assertEqual("approval", restored.required_actions[0]["type"])

    async def test_windows_replace_lock_does_not_abort_active_turn(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sessions.json"
            manager = TrueForgeSessionManager(FakeClient(), path)
            binding = SessionBinding("chat-locked", "work", "sess-test")
            with patch("app.integrations.trueforge.session_manager.os.replace", side_effect=PermissionError(5, "Access denied")):
                manager.record_event(binding, {"type": "turn.created", "turn_id": "turn-locked", "id": "evt-1"}, 1)
            restored = manager.get("chat-locked", "work")
            self.assertIsNotNone(restored)
            self.assertEqual("turn-locked", restored.active_turn_id)
            self.assertEqual(1, restored.last_sequence)
            self.assertTrue(path.is_file())


class RoutingAndProfileTests(unittest.TestCase):
    def test_profile_selection_and_deterministic_bypass(self):
        service = TrueForgeService()
        self.assertEqual("research", service.profile_for("research", "homework", "solve this"))
        self.assertEqual("work", service.profile_for("work", "research", "make a report"))
        self.assertEqual("code", service.profile_for("edit", "research", "debug this Python API endpoint"))
        self.assertFalse(service.should_route("edit", "open YouTube"))
        self.assertFalse(service.should_route("work", "Generate an image and post it on my LinkedIn"))
        self.assertFalse(service.should_route("work", "Read my latest Gmail message"))
        self.assertFalse(service.should_route("work", "Publish this announcement on Reddit"))
        self.assertFalse(service.should_route("work", "Generate an image about modern AI growth"))
        self.assertFalse(service.should_route("edit", "help me plan a product launch"))

    def test_work_profile_gates_write_adapters_and_code_uses_sandbox(self):
        work = build_manifest("work")
        code = build_manifest("code")
        self.assertEqual(
            ["work_execute", "browser_execute", "create_document", "create_pdf"],
            work["mcp_servers"][0]["require_approval_for_tools"],
        )
        self.assertEqual(16, work["config"]["iteration_limit"])
        self.assertEqual(TRUEFORGE_CODE_SANDBOX_ENABLED, code["config"]["sandbox"]["enabled"])
        self.assertFalse(work["config"]["sandbox"]["enabled"])
        self.assertIn("India", work["instructions"])

    def test_question_payload_uses_referenced_tool_call(self):
        service = TrueForgeService()
        binding = SessionBinding("chat-1", "general", "sess-test")
        binding.event_index["model-1"] = {
            "id": "model-1",
            "type": "model.message",
            "tool_calls": [{
                "id": "call-1",
                "function": {
                    "name": "ask_user_question",
                    "arguments": json.dumps({"question": "Which format?", "options": ["PDF", "DOCX"]}),
                },
            }],
        }
        payload = service._question_payload(binding, {
            "type": "tool.response_required",
            "thread_id": "main",
            "tool_calls": [{"id": "call-1", "source_event_id": "model-1"}],
        })
        self.assertEqual("Which format?", payload["questions"][0]["question"])
        self.assertEqual(["PDF", "DOCX"], payload["questions"][0]["options"])
        self.assertEqual("call-1", payload["questions"][0]["tool_call_id"])

    def test_tool_response_artifacts_are_forwarded_to_existing_ui_shape(self):
        service = TrueForgeService()
        artifacts = service._artifact_payload({
            "content": json.dumps({
                "artifacts": [{"name": "report.pdf", "path": "data/artifacts/report.pdf", "mime_type": "application/pdf"}]
            })
        })
        self.assertEqual([{"name": "report.pdf", "mime_type": "application/pdf"}], artifacts)


class ApprovalBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_deny_cancels_turn_instead_of_continuing_agent(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = TrueForgeService()
            client = FakeClient()
            service.client = client
            service.sessions = TrueForgeSessionManager(client, Path(temporary) / "sessions.json")
            binding = SessionBinding(
                "chat-deny", "work", "sess-deny",
                required_actions=[{"type": "tool.approval_required"}],
            )
            service.sessions.save(binding)
            events = [
                event async for event in service.approve(
                    "chat-deny", "work", "call-1", "main", False
                )
            ]
            self.assertEqual(["sess-deny"], client.cancelled)
            self.assertEqual("tool_denied", events[0]["activity"]["event"])
            self.assertEqual("cancelled", events[1]["harness"]["status"])
            self.assertEqual([], service.sessions.get("chat-deny", "work").required_actions)

    async def test_rate_limit_retry_continues_same_session_without_auto_approving_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = TrueForgeService()
            client = RateLimitedClient()
            service.client = client
            service.sessions = TrueForgeSessionManager(client, Path(temporary) / "sessions.json")
            service.sessions.save(SessionBinding("chat-retry", "work", "sess-retry", active_turn_id="turn-1"))
            events = [event async for event in service.retry_rate_limited("chat-retry", "work")]
            self.assertEqual("completed", events[-1]["harness"]["status"])
            continuation = client.inputs[0][0]["content"]
            self.assertIn("Do not repeat completed tool actions", continuation)
            self.assertIn("Ask for approval again", continuation)
