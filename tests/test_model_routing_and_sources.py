import json
import tempfile
import base64
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import config
from app.services.groq_service import _friendly_model_error
from app.services.model_router import ModelRouter, test_model_connections as check_model_connections
from app.main import _is_model_identity_query, _model_identity_answer
from app.services.research_service import ResearchMissionService
from app.services.research_mode_service import ResearchModeService
from app.services.trueforge_service import TrueForgeService


class ModelRouterTests(unittest.TestCase):
    def test_rate_limit_rotates_from_groq_to_gemini(self):
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Gemini fallback", tool_calls=[]))])
        router = ModelRouter()
        with (
            patch.object(config, "GROQ_API_KEYS", ["groq-test"]),
            patch.object(config, "GEMINI_API_KEY", "gemini-test"),
            patch.object(config, "MODEL_PROVIDER_ORDER", "groq,gemini"),
            patch("groq.Groq") as groq_client,
            patch.object(router, "_gemini_create", return_value=response) as gemini,
        ):
            groq_client.return_value.chat.completions.create.side_effect = RuntimeError("429 tokens per day quota reached")
            result = router.create(model="test", messages=[{"role": "user", "content": "hello"}])

        self.assertEqual(result.choices[0].message.content, "Gemini fallback")
        self.assertEqual(router.status()["last_provider"], "gemini")
        self.assertEqual(router.status()["failovers"], 1)
        gemini.assert_called_once()

    def test_connection_failure_rotates_to_next_provider_without_calling_it_a_rate_limit(self):
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Gemini fallback", tool_calls=[]))])
        router = ModelRouter()
        with (
            patch.object(config, "GROQ_API_KEYS", ["groq-test"]),
            patch.object(config, "GEMINI_API_KEY", "gemini-test"),
            patch.object(config, "MODEL_PROVIDER_ORDER", "groq,gemini"),
            patch("groq.Groq") as groq_client,
            patch.object(router, "_gemini_create", return_value=response),
        ):
            groq_client.return_value.chat.completions.create.side_effect = RuntimeError("Connection reset")
            result = router.create(model="test", messages=[{"role": "user", "content": "hello"}])

        self.assertEqual(result.choices[0].message.content, "Gemini fallback")
        self.assertEqual(router.status()["last_provider"], "gemini")
        self.assertEqual(router._cooldown_kinds["groq:1"], "connection")

    def test_connection_cooldown_is_not_reported_as_rate_limit(self):
        router = ModelRouter()
        router._cooldowns["gemini:1"] = __import__("time").time() + 20
        router._cooldown_kinds["gemini:1"] = "connection"
        message = str(router._cooldown_error())
        self.assertIn("connection errors", message)
        self.assertNotIn("rate-limited", message)

    def test_explicit_unconfigured_provider_has_clear_error(self):
        router = ModelRouter()
        with (
            patch.object(config, "GROQ_API_KEYS", []),
            patch.object(config, "GEMINI_API_KEY", ""),
            patch.object(config, "OPENROUTER_API_KEY", ""),
        ):
            with self.assertRaisesRegex(RuntimeError, "Openrouter is not configured"):
                router.create(
                    preference="openrouter:openrouter/free",
                    model="ignored",
                    messages=[{"role": "user", "content": "hello"}],
                )

    def test_connection_test_uses_global_saved_providers_without_generating_text(self):
        response = Mock(status_code=200)
        with (
            patch.object(config, "GROQ_API_KEYS", ["groq-test"]),
            patch.object(config, "GEMINI_API_KEY", ""),
            patch.object(config, "OPENROUTER_API_KEY", ""),
            patch("app.services.model_router.requests.get", return_value=response) as request,
        ):
            result = check_model_connections()
        self.assertEqual(result["providers"]["groq"]["status"], "connected")
        self.assertEqual(result["providers"]["gemini"]["status"], "not_configured")
        self.assertEqual(request.call_count, 1)

    def test_windows_socket_block_has_actionable_model_message(self):
        message = _friendly_model_error(RuntimeError("[WinError 10013] forbidden by its access permissions"))
        self.assertIn("Windows blocked", message)
        self.assertIn("Firewall", message)

    def test_selected_nemotron_identity_is_deterministic(self):
        router = ModelRouter()
        preference = "openrouter:nvidia/nemotron-3.5-lightning:free"
        with patch.object(config, "OPENROUTER_API_KEY", "openrouter-test"):
            details = router.describe_selection(preference)
            answer, answer_details = _model_identity_answer(preference)
        self.assertEqual(details["model"], "nvidia/nemotron-3.5-lightning:free")
        self.assertEqual(details["label"], "NVIDIA Nemotron 3.5 Lightning (free)")
        self.assertIn("Normal prompts use that exact selection", answer)
        self.assertEqual(answer_details["provider"], "openrouter")
        self.assertNotIn("GPT-4", answer)

    def test_model_identity_question_typo_uses_fast_local_route(self):
        self.assertTrue(_is_model_identity_query("whihc model am i runnning"))
        self.assertTrue(_is_model_identity_query("what api model is this"))
        self.assertFalse(_is_model_identity_query("which model should I use for programming"))

    def test_research_source_discovery_always_returns_a_pair(self):
        service = ResearchMissionService()
        tavily_client = Mock()
        tavily_client.return_value.search.return_value = {
            "answer": "overview",
            "results": [{"title": "Source", "url": "https://example.com"}],
        }
        fake_module = SimpleNamespace(TavilyClient=tavily_client)
        with (
            patch("app.services.research_service.TAVILY_API_KEY", "test"),
            patch.dict("sys.modules", {"tavily": fake_module}),
        ):
            sources, answer = service._discover_sources("test query")
        self.assertEqual(answer, "overview")
        self.assertEqual(sources[0]["url"], "https://example.com")


class ResearchSourceTests(unittest.TestCase):
    def _service(self, root: Path) -> ResearchModeService:
        service = ResearchModeService()
        service.jobs_dir = root / "jobs"
        service.images_dir = root / "images"
        service.files_dir = root / "files"
        service.sources_dir = root / "sources"
        for directory in (service.jobs_dir, service.images_dir, service.files_dir, service.sources_dir):
            directory.mkdir()
        return service

    def test_text_upload_is_chunked_and_retrieved_for_homework_chat(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = self._service(Path(temporary))
            service._reason = Mock(return_value="Grounded answer")
            result = service.run(
                "Explain photosynthesis",
                "homework",
                [],
                [],
                "chat",
                [{"name": "biology-notes.txt", "content": "Photosynthesis converts light energy into chemical energy in plants."}],
                "student-session",
            )

            evidence = service._reason.call_args.args[1]
            stored = list((service.sources_dir / "student-session").glob("*.json"))

        self.assertIn("Photosynthesis converts", evidence)
        self.assertEqual(len(stored), 1)
        self.assertIn("sources_imported", [item["event"] for item in result["activities"]])
        self.assertIn("source_retrieval", [item["event"] for item in result["activities"]])

    def test_youtube_source_imports_public_caption_transcript(self):
        page = Mock()
        page.raise_for_status.return_value = None
        page.text = '<html><title>Biology Lesson - YouTube</title>"captionTracks":[{"baseUrl":"https://captions.test/api?x=1\\u0026y=2","languageCode":"en"}],"audioTracks":[]</html>'
        captions = Mock()
        captions.raise_for_status.return_value = None
        captions.json.return_value = {"events": [{"segs": [{"utf8": "Cells use energy. "}]}, {"segs": [{"utf8": "ATP stores it."}]}]}
        with tempfile.TemporaryDirectory() as temporary:
            service = self._service(Path(temporary))
            with patch("app.services.research_mode_service.requests.get", side_effect=[page, captions]):
                source = service._import_youtube_source("yt-session", "https://youtu.be/abc123DEF45")
            record = json.loads(next((service.sources_dir / "yt-session").glob("*.json")).read_text(encoding="utf-8"))

        self.assertEqual(source["type"], "youtube")
        self.assertEqual(record["name"], "Biology Lesson")
        self.assertIn("ATP stores it", record["chunks"][0])

    def test_pdf_document_is_extracted_then_chunked_as_a_session_source(self):
        import fitz

        document = fitz.open()
        for number in range(1, 8):
            page = document.new_page()
            page.insert_text((72, 72), f"Research page {number}: renewable energy evidence and findings.")
        encoded = base64.b64encode(document.tobytes()).decode("ascii")
        document.close()
        with tempfile.TemporaryDirectory() as temporary:
            service = self._service(Path(temporary))
            records = service._store_text_attachments("pdf-session", [{
                "name": "research-paper.pdf",
                "content": f"data:application/pdf;base64,{encoded}",
            }])
            stored = json.loads(next((service.sources_dir / "pdf-session").glob("*.json")).read_text(encoding="utf-8"))

        self.assertEqual("pdf", records[0]["type"])
        self.assertIn("[Page 7]", "\n".join(stored["chunks"]))
        self.assertGreater(stored["token_count"], 20)


class ResearchRoutingTests(unittest.TestCase):
    def test_research_uses_source_grounded_pipeline_not_trueforge(self):
        service = TrueForgeService()
        with patch.object(type(service), "enabled", new_callable=unittest.mock.PropertyMock, return_value=True):
            self.assertFalse(service.should_route("research", "Summarize my source"))

    def test_frontend_contains_branch_activity_upload_choices_and_provider_settings(self):
        root = Path(__file__).parents[1]
        script = (root / "frontend" / "script.js").read_text(encoding="utf-8")
        html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
        self.assertIn("function showResearchUploadChooser", script)
        self.assertIn("currentResearchBranch === 'research'", script)
        self.assertIn('id="research-source-url"', html)
        self.assertIn('id="model-settings-save"', html)
        self.assertIn('id="model-settings-test"', html)
        self.assertIn("saved globally", script)
        self.assertIn("model.speed === 'fast'", script)
        self.assertIn('id="chat-model-selector"', html)
        self.assertIn('id="model-openrouter-key"', html)
        self.assertIn("researchSourceControl.hidden = !isHomework", script)
        self.assertNotIn("chatModelSelector.hidden = isHomework", script)
        self.assertIn("Gemini is the Homework default", script)
        self.assertIn('id="research-source-manager"', html)
        self.assertIn("loadResearchSources", script)
        self.assertIn("model_preference", script)
        self.assertIn("text_attachments", script)
        self.assertIn("application/pdf", html)
        self.assertIn("function documentFileToContent", script)
        self.assertIn("function isInstructionlessResearchContent", script)
        self.assertIn("Pasted research source.txt", script)


if __name__ == "__main__":
    unittest.main()
