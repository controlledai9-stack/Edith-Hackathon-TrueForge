import importlib.util
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path

from app.utils.speech import prepare_tts_text


class SpeechCleanupTests(unittest.TestCase):
    def test_removes_bare_url_and_numeric_citation(self):
        result = prepare_tts_text(
            "Claude's new model is faster [1]. See https://claude.ai/news for details."
        )
        self.assertEqual(result, "Claude's new model is faster.")
        self.assertNotIn("https", result.lower())

    def test_keeps_markdown_link_label_and_drops_sources_section(self):
        result = prepare_tts_text(
            "The practical conclusion is clear. Read [Anthropic's update](https://example.com).\n"
            "Sources:\n- https://example.com"
        )
        self.assertEqual(result, "The practical conclusion is clear. Read Anthropic's update.")


class WatchlistDeadlockTests(unittest.TestCase):
    def test_add_returns_and_writes_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_config = types.ModuleType("config")
            fake_config.WATCHLISTS_FILE = root / "watchlists.json"
            fake_config.MONITORING_HISTORY_DIR = root / "history"
            fake_config.MONITORING_HISTORY_DIR.mkdir()
            fake_config.TAVILY_API_KEY = ""

            fake_scraper_module = types.ModuleType("app.services.scraper_service")
            fake_scraper_module.get_scraper_service = lambda: object()
            fake_scraper_module.expected_fields_for = lambda category: None

            original_config = sys.modules.get("config")
            original_scraper = sys.modules.get("app.services.scraper_service")
            sys.modules["config"] = fake_config
            sys.modules["app.services.scraper_service"] = fake_scraper_module
            try:
                module_path = Path(__file__).parents[1] / "app" / "services" / "watchlist_service.py"
                spec = importlib.util.spec_from_file_location("watchlist_regression_module", module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                service = module.WatchlistService()

                result = {}
                worker = threading.Thread(
                    target=lambda: result.update(service.add_watchlist("Google", ["AI"]))
                )
                worker.start()
                worker.join(timeout=1)

                self.assertFalse(worker.is_alive(), "add_watchlist deadlocked while logging history")
                self.assertEqual(result["name"], "Google")
                events = service.get_history()
                self.assertEqual(events[0]["type"], "watchlist_created")
            finally:
                if original_config is None:
                    sys.modules.pop("config", None)
                else:
                    sys.modules["config"] = original_config
                if original_scraper is None:
                    sys.modules.pop("app.services.scraper_service", None)
                else:
                    sys.modules["app.services.scraper_service"] = original_scraper


class WorkModeUITests(unittest.TestCase):
    def test_visible_mode_switch_routes_work_requests(self):
        script = (Path(__file__).parents[1] / "frontend" / "script.js").read_text(encoding="utf-8")
        set_mode = script[script.index("function setMode(mode, announce = true)"):script.index("function newChat()")]
        self.assertIn("new Set(['edit', 'work', 'research'])", set_mode)
        self.assertIn("btnResearch.classList.toggle('active', isResearch)", set_mode)
        self.assertIn("mode: currentMode", script)

    def test_plugin_manager_loads_registry(self):
        script = (Path(__file__).parents[1] / "frontend" / "script.js").read_text(encoding="utf-8")
        self.assertIn("async function openPluginManager()", script)
        self.assertIn("fetch(`${API}/plugins`)", script)

    def test_external_actions_keep_a_clickable_deployment_fallback(self):
        script = (Path(__file__).parents[1] / "frontend" / "script.js").read_text(encoding="utf-8")
        self.assertIn("prepareExternalWindow(text)", script)
        self.assertIn("Direct link · opens here if new tabs are blocked", script)
        self.assertIn("anchor.target = link.sameTabFallback ? '_self' : '_blank'", script)
        self.assertIn("inferDirectOpenUrl(text)", script)
        self.assertIn("sameExternalDestination(pendingExternalUrl, destination)", script)
        self.assertIn("window.open(pendingExternalUrl || 'about:blank', 'edith-external')", script)
        self.assertIn("window.location.assign(sameTabDestination)", script)

    def test_quick_start_contains_two_guide_pages(self):
        html = (Path(__file__).parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(html.count('data-guide-page="'), 2)
        self.assertIn("Work Mode commands", html)
        self.assertIn("Header and controls", html)

    def test_homework_board_loads_math_renderer(self):
        root = Path(__file__).parents[1]
        html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
        script = (root / "frontend" / "script.js").read_text(encoding="utf-8")
        self.assertIn("tex-svg.js", html)
        self.assertIn("MathJax.typesetPromise([solution])", script)
        self.assertIn('class="homework-equation"', script)
        self.assertIn('class="homework-answer"', script)
        self.assertIn("const boldQuestion", script)
        self.assertIn(r".replace(/(^|[^\\])\\\[/g, '$1$$$$')", script)
        self.assertNotIn(r".replace(/\\\\([\[\]()])/g", script)

    def test_india_greeting_has_disjoint_time_ranges_and_refreshes(self):
        script = (Path(__file__).parents[1] / "frontend" / "script.js").read_text(encoding="utf-8")
        self.assertIn("timestamp + (330 * 60 * 1000)", script)
        self.assertIn("if (h >= 12 && h < 17) return 'Good afternoon.'", script)
        self.assertIn("if (h >= 17 && h < 22) return 'Good evening.'", script)
        self.assertIn("return 'Burning the midnight oil?'", script)
        self.assertIn("window.setInterval(setGreeting, 60_000)", script)

    def test_modes_have_isolated_conversations_and_research_activity_is_branch_aware(self):
        script = (Path(__file__).parents[1] / "frontend" / "script.js").read_text(encoding="utf-8")
        self.assertIn("const workspaceStates = new Map()", script)
        self.assertIn("saveWorkspaceState(activeWorkspaceKey)", script)
        self.assertIn("restoreWorkspaceState(activeWorkspaceKey)", script)
        self.assertIn("state.searchOpen = !!searchResultsWidget?.classList.contains('open')", script)
        self.assertIn("currentResearchBranch === 'research'", script)
        self.assertIn("if (isHomework && activityPanel)", script)

    def test_work_mode_supports_browser_tasks_and_image_handoffs(self):
        root = Path(__file__).parents[1]
        script = (root / "frontend" / "script.js").read_text(encoding="utf-8")
        main = (root / "app" / "main.py").read_text(encoding="utf-8")
        work = (root / "app" / "services" / "work_mode_service.py").read_text(encoding="utf-8")
        self.assertIn("actions.browser_tasks", script)
        self.assertIn("Browser Operator", script)
        self.assertIn("currentMode === 'research' || currentMode === 'work'", script)
        self.assertIn("work_images", main)
        self.assertIn("_build_plan", work)
        self.assertIn('MAX_TOOL_STEPS", "16"', work)
        self.assertIn("auto_approve_safe_work", main)
        self.assertIn("autoApproveSafeWork", script)
        self.assertIn("Never invent a confirmation ID", work)

    def test_universal_browser_uses_a_native_side_window_without_a_screenshot_preview(self):
        root = Path(__file__).parents[1]
        worker = (root / "app" / "services" / "universal_browser_worker.py").read_text(encoding="utf-8")
        main = (root / "app" / "main.py").read_text(encoding="utf-8")
        script = (root / "frontend" / "script.js").read_text(encoding="utf-8")
        work = (root / "app" / "services" / "work_mode_service.py").read_text(encoding="utf-8")
        self.assertIn('UNIVERSAL_BROWSER_HEADLESS", "false"', worker)
        self.assertIn("_native_window_geometry", worker)
        self.assertIn('f"--window-position={left},{top}"', worker)
        self.assertIn('f"--window-size={width},{height}"', worker)
        self.assertIn("universal-browser-handoff", script)
        self.assertNotIn("universal-browser-preview", script)
        self.assertIn("_resolve_pending_confirmation", work)
        self.assertIn("_is_linkedin_publish_request", work)
        self.assertIn("_stage_linkedin_post", work)
        self.assertIn("linkedin_publish", work)
        self.assertIn("msg-upload-image", script)
        self.assertIn("browser_jobs", script)
        self.assertIn("pollUniversalBrowserJob", script)
        self.assertIn('"--disable-quic"', worker)
        self.assertIn('task.get("action_type") == "navigate"', worker)
        self.assertIn('"open_immediately": True', (root / "app" / "plugins" / "browser_operator.py").read_text(encoding="utf-8"))
        self.assertIn("if (task.open_immediately)", script)
        self.assertNotIn('/browser/jobs/${encodeURIComponent(jobId)}/interact', script)
        self.assertNotIn('universal-browser-input-capture', script)
        self.assertNotIn('queueUniversalBrowserInteraction', script)
        self.assertIn('Browser opened beside E.D.I.T.H.', worker)

    def test_cancel_and_completion_finalize_thinking_indicators(self):
        root = Path(__file__).parents[1]
        script = (root / "frontend" / "script.js").read_text(encoding="utf-8")
        main = (root / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("function finalizePendingAssistantIndicators", script)
        self.assertIn("finalizePendingAssistantIndicators();\n    setStreamingControls(false);", script)
        self.assertGreaterEqual(script.count("finalizePendingAssistantIndicators();"), 3)
        self.assertIn('/chat/sessions/${encodeURIComponent(sessionId)}/cancel-turn', script)
        self.assertIn('@app.post("/chat/sessions/{session_id}/cancel-turn")', main)
        self.assertIn("stream_task.cancel()", main)
        self.assertIn("_active_chat_streams.pop(session_id, None)", main)

    def test_linkedin_caption_is_rechecked_after_media_and_verified_on_the_post(self):
        root = Path(__file__).parents[1]
        worker = (root / "app" / "services" / "universal_browser_worker.py").read_text(encoding="utf-8")
        upload = worker.index('set_input_files([item["path"] for item in files[:5]]')
        second_caption_check = worker.index("_ensure_linkedin_caption(page, context_text)", upload)
        self.assertGreater(second_caption_check, upload)
        self.assertIn("success_confirmation_seen", worker)
        self.assertIn("repair_latest_linkedin_caption(page, profile_activity_url, context_text)", worker)
        self.assertIn("if not context_text and not files", worker)
        self.assertIn("The confirmed media-only post is visible", worker)

    def test_plugin_dashboard_has_an_installable_store_and_manifest_url(self):
        root = Path(__file__).parents[1]
        html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
        script = (root / "frontend" / "script.js").read_text(encoding="utf-8")
        main = (root / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn('id="plugin-store-tab"', html)
        self.assertIn("installStorePlugin", script)
        self.assertIn("installPluginManifest", script)
        self.assertIn('@app.get("/plugins/store")', main)
        self.assertIn('@app.post("/plugins/store/install-manifest")', main)
        self.assertIn("modelcontextprotocol/servers", html)
        self.assertIn("youtube.com/watch?v=CQywdSdi5iA", html)
        self.assertIn("A normal GitHub repository page is not an install URL", html)
        self.assertIn("plugin-website-link", script)

    def test_startup_does_not_silently_create_a_second_server(self):
        root = Path(__file__).parents[1]
        startup = (root / "run.py").read_text(encoding="utf-8")
        self.assertIn("EDITH_ALLOW_PORT_FALLBACK", startup)
        self.assertIn("already occupied by another E.D.I.T.H. server", startup)

    def test_general_stream_renders_markdown_without_a_literal_cursor(self):
        root = Path(__file__).parents[1]
        script = (root / "frontend" / "script.js").read_text(encoding="utf-8")
        style = (root / "frontend" / "style.css").read_text(encoding="utf-8")
        self.assertIn("function formatAssistantMarkdown", script)
        self.assertIn("formatAssistantMarkdown(fullResponse, final)", script)
        self.assertNotIn("cursorEl.textContent = '|'", script)
        self.assertIn("width: fit-content", style)
        self.assertNotIn("msg-stream-text.is-streaming::after", style)
        self.assertIn("stream-progress-ring", style)
        self.assertIn("E.D.I.T.H. is continuing the response", script)

    def test_welcome_is_india_timed_and_actions_are_mode_specific(self):
        root = Path(__file__).parents[1]
        script = (root / "frontend" / "script.js").read_text(encoding="utf-8")
        self.assertIn("data-time-zone=\"Asia/Kolkata\"", script)
        self.assertIn("function indiaGreeting", script)
        self.assertIn("function welcomeActionsForMode", script)
        self.assertIn("Create sample PPT", script)
        self.assertIn("Create sample Excel", script)
        self.assertIn("if (currentMode === 'research') return []", script)

    def test_research_file_opens_in_editor_and_download_is_explicit(self):
        root = Path(__file__).parents[1]
        html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
        script = (root / "frontend" / "script.js").read_text(encoding="utf-8")
        main = (root / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn('id="research-editor-content"', html)
        self.assertIn('id="research-editor-save"', html)
        self.assertIn('id="research-editor-download"', html)
        self.assertIn("openResearchFileEditor", script)
        self.assertIn("method: 'PUT'", script)
        self.assertIn("new Blob([researchEditorContent.value]", script)
        self.assertIn('@app.put("/research-mode/files/{category}/{filename}/content")', main)

    def test_trueforge_controls_support_stop_deny_and_rate_limit_resume(self):
        root = Path(__file__).parents[1]
        html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
        script = (root / "frontend" / "script.js").read_text(encoding="utf-8")
        main = (root / "app" / "main.py").read_text(encoding="utf-8")
        service = (root / "app" / "services" / "trueforge_service.py").read_text(encoding="utf-8")
        self.assertIn('id="stop-task-button"', html)
        self.assertIn("scheduleHarnessAutoResume", script)
        self.assertIn('retry-rate-limit', main)
        self.assertIn("await self.client.cancel(binding.harness_session_id)", service)
        self.assertIn('"mcp_available": edith_mcp is not None', main)
        self.assertIn('harness_health.get("ok") and edith_mcp is not None', main)


class ScrapeSummaryTests(unittest.TestCase):
    def test_missing_model_does_not_dump_raw_scrape(self):
        fake_config = types.ModuleType("config")
        fake_config.GROQ_API_KEYS = []
        fake_config.GROQ_MODEL = "unused"
        fake_config.JARVIS_SYSTEM_PROMPT = ""
        fake_config.GENERAL_CHAT_ADDENDUM = ""
        fake_config.load_user_context = lambda: ""

        fake_time = types.ModuleType("app.utils.time_info")
        fake_time.current_time_context = lambda: ""
        fake_vector = types.ModuleType("app.services.vector_store")
        fake_vector.get_memory_store = lambda: None

        replacements = {
            "config": fake_config,
            "app.utils.time_info": fake_time,
            "app.services.vector_store": fake_vector,
        }
        originals = {name: sys.modules.get(name) for name in replacements}
        sys.modules.update(replacements)
        try:
            module_path = Path(__file__).parents[1] / "app" / "services" / "groq_service.py"
            spec = importlib.util.spec_from_file_location("groq_summary_regression_module", module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            service = module.GroqService()
            raw = "Google Flow Create with Google Flow START NOW repeated navigation"
            answer = service.summarize_scrape(raw, "https://example.com")
            self.assertNotIn(raw, answer)
            self.assertIn("summarizer", answer.lower())
        finally:
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original


class VisionServiceTests(unittest.TestCase):
    def test_uses_non_thinking_mode_and_accepts_data_urls(self):
        fake_config = types.ModuleType("config")
        fake_config.GROQ_API_KEYS = []
        fake_config.GROQ_VISION_MODEL = "qwen/qwen3.6-27b"
        fake_config.VISION_MAX_IMAGE_BYTES = 5_000_000
        original_config = sys.modules.get("config")
        sys.modules["config"] = fake_config
        try:
            module_path = Path(__file__).parents[1] / "app" / "services" / "vision_service.py"
            spec = importlib.util.spec_from_file_location("vision_regression_module", module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            calls = []

            class Completions:
                def create(self, **kwargs):
                    calls.append(kwargs)
                    message = types.SimpleNamespace(content="I can see the uploaded image.")
                    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

            client = types.SimpleNamespace(
                chat=types.SimpleNamespace(completions=Completions())
            )
            service = module.VisionService.__new__(module.VisionService)
            service._clients = [client]
            answer = service.analyze("data:image/jpeg;base64,/9j/2Q==", "What is this?")

            self.assertEqual(answer, "I can see the uploaded image.")
            self.assertEqual(calls[0]["reasoning_effort"], "none")
            self.assertEqual(calls[0]["max_completion_tokens"], 1024)
            image_url = calls[0]["messages"][1]["content"][1]["image_url"]["url"]
            self.assertEqual(image_url, "data:image/jpeg;base64,/9j/2Q==")
        finally:
            if original_config is None:
                sys.modules.pop("config", None)
            else:
                sys.modules["config"] = original_config


class ScanChangeReportTests(unittest.TestCase):
    def test_scan_report_includes_change_details_and_source(self):
        from app.services.change_detection_service import format_scan_change_report

        results = [{
            "entity": "NVIDIA",
            "results": [{
                "category": "news",
                "changes": [{
                    "change_type": "value_change", "field": "market_cap",
                    "before": 12.4, "after": 11.9, "percentage_change": -4.03,
                    "source_url": "https://example.com/nvidia",
                }],
            }],
        }]
        report = format_scan_change_report(results)

        self.assertIn("1 change detected", report)
        self.assertIn("NVIDIA · news", report)
        self.assertIn("market_cap changed from 12.4 to 11.9 (-4.03%)", report)
        self.assertIn("Source: https://example.com/nvidia", report)

    def test_long_text_change_reports_exact_fragments(self):
        from app.services.change_detection_service import summarize_change

        summary = summarize_change({
            "change_type": "text_change", "field": "text",
            "before": "Post engagement was 322 and total views were 260K",
            "after": "Post engagement was 323 and total views were 261K",
        })
        self.assertIn("“322” → “323”", summary)
        self.assertIn("“260K” → “261K”", summary)


if __name__ == "__main__":
    unittest.main()
