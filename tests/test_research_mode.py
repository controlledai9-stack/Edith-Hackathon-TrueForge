import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from app.models import ChatRequest
from app.services.research_mode_service import ResearchModeService
from config import GROQ_HOMEWORK_MODEL


class ResearchModeModelTests(unittest.TestCase):
    def test_homework_reasoning_uses_qwen_36(self):
        self.assertEqual(GROQ_HOMEWORK_MODEL, "qwen/qwen3.6-27b")

    def test_chat_request_accepts_research_homework_and_image_batch(self):
        request = ChatRequest(
            message="Solve these",
            mode="research",
            research_branch="homework",
            homework_output="chat",
            imgbase64s=["a", "b"],
        )
        self.assertEqual(request.mode, "research")
        self.assertEqual(request.research_branch, "homework")
        self.assertEqual(request.homework_output, "chat")
        self.assertEqual(len(request.imgbase64s), 2)


class ResearchModePipelineTests(unittest.TestCase):
    def test_generic_vision_refusal_uses_fallback_instead_of_whiteboard(self):
        service = ResearchModeService()
        service._gemini_scan = Mock(return_value="I'm sorry, but I can't help with that.")
        service.fallback_vision = Mock()
        service.fallback_vision.analyze.return_value = "Question 2: determine whether X and Y are independent."

        evidence = service._scan_images(
            [{"index": 1, "base64": "placeholder"}], "homework", "Solve this question"
        )

        self.assertIn("Question 2", evidence)
        self.assertNotIn("can't help", evidence)
        service.fallback_vision.analyze.assert_called_once()

    def test_all_vision_refusals_become_a_clear_upload_error(self):
        service = ResearchModeService()
        service._gemini_scan = Mock(return_value="I’m sorry, but I can’t help with that.")
        service.fallback_vision = Mock()
        service.fallback_vision.analyze.return_value = "I cannot help with that."

        with self.assertRaisesRegex(RuntimeError, "clearer crop"):
            service._scan_images(
                [{"index": 1, "base64": "placeholder"}], "homework", "Solve this question"
            )

        self.assertTrue(service._is_vision_refusal("I’m sorry, but I can’t provide that assistance."))

    def test_homework_pipeline_saves_snap_queue_and_returns_steps(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = ResearchModeService()
            service.jobs_dir = Path(temporary) / "jobs"
            service.images_dir = Path(temporary) / "images"
            service.files_dir = Path(temporary) / "files"
            service.jobs_dir.mkdir()
            service.images_dir.mkdir()
            service.files_dir.mkdir()
            service._scan_images = Mock(return_value="Problem 1: 2 + 2")
            service._reason = Mock(return_value="Problem 1\nFinal answer: 4\nSteps: Add 2 and 2.")
            encoded = base64.b64encode(b"small-jpeg-placeholder").decode("ascii")

            result = service.run("Solve everything", "homework", [encoded, encoded], [])

            self.assertIn("Final answer: 4", result["reply"])
            self.assertEqual(len(result["artifacts"]), 1)
            self.assertEqual(result["artifacts"][0]["mime_type"], "text/markdown")
            events = [activity["event"] for activity in result["activities"]]
            self.assertEqual(
                events,
                ["research_route", "snap_queued", "screen_scan", "reasoning", "batch_solved"],
            )
            saved_job = json.loads(next(service.jobs_dir.glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(saved_job["status"], "completed")
            self.assertEqual(saved_job["image_count"], 2)
            self.assertEqual(len(list(service.images_dir.glob("*.jpg"))), 2)
            method_file = next(service.files_dir.glob("*.md"))
            method_text = method_file.read_text(encoding="utf-8")
            self.assertIn("E.D.I.T.H. Homework Methods", method_text)
            self.assertIn("**Method:**", method_text)
            self.assertIn("**Formula(s):**", method_text)
            self.assertIn("## Formula Sheet", method_text)
            self.assertNotIn("## Full Worked Solution", method_text)

    def test_latex_cleanup_and_compact_method_file(self):
        raw = (
            "## Question 14 — PDF normalization and moments\n\n"
            "**What is asked:** Find the moments.\n\n"
            "**Method:** Normalize with $\\int f_X(x)\\,dx=1$.\n\n"
            "**Formula(s):**\n- $\\displaystyle E[X]=\\int_0^1 x f_X(x)\\,dx$\n"
            "- $\\boxed{Var(X)=\\frac{1}{10}}$\n\n"
            "**Working:** $$\\tfrac12 + \\tfrac{x^{3}}{3} + x^{2}$$\n\n"
            "**Final answer:** $\\boxed{\\tfrac1{10}}$\n\n"
            "## Formula Index\n| Formula | Q |\n|---|---|\n| raw | 14 |"
        )
        with tempfile.TemporaryDirectory() as temporary:
            service = ResearchModeService()
            service.files_dir = Path(temporary)
            display, records = service._prepare_homework_reply(raw)
            artifact = service._create_homework_file(records)
            method_text = Path(artifact["path"]).read_text(encoding="utf-8")

            self.assertIn("## Question 14 — PDF normalization and moments", display)
            self.assertIn("$$\\tfrac12", display)
            self.assertIn("$\\boxed", display)
            self.assertNotIn("**Method:**", display)
            self.assertNotIn("**Formula(s):**", display)
            self.assertNotIn("Formula Index", display)
            self.assertIn("### Calculation", display)
            self.assertIn("**Answer:**", display)
            self.assertIn("## Formula Sheet", method_text)
            self.assertIn("∫[0 to 1]", method_text)
            self.assertNotIn("**Working:**", method_text)
            self.assertNotIn("**Final answer:**", method_text)
            self.assertIn("Φ", service._clean_math_notation(r"\Phi(A^c) = 1-\phi(A)"))
            self.assertIn("Aᶜ", service._clean_math_notation(r"\Phi(A^c) = 1-\phi(A)"))

    def test_raw_thinking_is_removed_but_method_record_is_preserved(self):
        raw = (
            "<think>Analyze User Input:\nHidden planning and self-correction.</think>\n"
            "## Question 2 — Independence\n\n"
            "**What is asked:** Decide whether X and Y are independent.\n\n"
            "**Method:** Factor the joint density.\n\n"
            "**Formula(s):** $f_{XY}(x,y)=f_X(x)f_Y(y)$\n\n"
            "**Working:** 1. Compute both marginals.\n\n"
            "**Final answer:** Yes.\n\n"
            "## Formula Index\n- Question 2: independence formula"
        )
        service = ResearchModeService()
        display, records = service._prepare_homework_reply(raw)

        self.assertNotIn("think", display.lower())
        self.assertNotIn("Analyze User Input", display)
        self.assertNotIn("Formula Index", display)
        self.assertNotIn("**Formula(s):**", display)
        self.assertEqual(records[0]["method"], "Factor the joint density.")
        self.assertIn("f{XY}(x,y)", records[0]["formulas"].replace("_", ""))

    def test_unclosed_thinking_block_is_not_displayed(self):
        service = ResearchModeService()
        self.assertEqual(service._strip_model_scaffolding("<think>Hidden unfinished reasoning"), "")

    def test_incomplete_whiteboard_draft_is_detected(self):
        service = ResearchModeService()
        incomplete = (
            "## Question 1 — Conditional Probability\n\n"
            "**What is asked:** Find the conditional probability.\n\n"
            "**Method:** Use Bayes' theorem.\n\n"
            "**Formula(s):** $P(A|B)="
        )
        complete = (
            "## Question 1 — Conditional Probability\n\n"
            "**What is asked:** Find the conditional probability.\n\n"
            "**Method:** Use Bayes' theorem.\n\n"
            "**Formula(s):** $P(A|B)=P(A\\cap B)/P(B)$\n\n"
            "**Working:** 1. Substitute the joint and marginal probabilities.\n2. Divide to obtain $0.25$.\n\n"
            "**Final answer:** $\\boxed{0.25}$\n\n"
            "**Quick check:** The result is between zero and one."
        )

        self.assertFalse(service._is_complete_homework_solution(incomplete))
        self.assertTrue(service._is_complete_homework_solution(complete))
        display, records = service._prepare_homework_reply(complete)
        self.assertIn("Substitute the joint", display)
        self.assertIn("**Check:**", display)
        self.assertNotIn("Use Bayes' theorem", display)
        self.assertEqual("Use Bayes' theorem.", records[0]["method"])

    def test_sidebar_question_creates_no_file_or_formula_sheet(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = ResearchModeService()
            service.jobs_dir = Path(temporary) / "jobs"
            service.images_dir = Path(temporary) / "images"
            service.files_dir = Path(temporary) / "files"
            service.jobs_dir.mkdir()
            service.images_dir.mkdir()
            service.files_dir.mkdir()
            service._reason = Mock(return_value=r"The symbol \phi means phi. No file needed.")

            result = service.run("What does phi mean?", "homework", [], [], "chat")

            self.assertEqual(result["artifacts"], [])
            self.assertNotIn("Formula Sheet", result["reply"])
            self.assertIn("φ", result["reply"])
            self.assertEqual(list(service.files_dir.glob("*.md")), [])

    def test_board_batches_merge_into_one_cumulative_method_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = ResearchModeService()
            service.files_dir = Path(temporary)
            _, first = service._prepare_homework_reply(
                "## Question 3 — Probability\n\n**Method:** Count outcomes.\n\n**Formula(s):** P=good/total\n\n**Working:** done"
            )
            _, second = service._prepare_homework_reply(
                "## Question 7 — Matrices\n\n**Method:** Row reduction.\n\n**Formula(s):** Ax=b\n\n**Working:** done"
            )
            service._create_homework_file(first)
            service._create_homework_file(second)
            files = list(service.files_dir.glob("*.md"))
            text = files[0].read_text(encoding="utf-8")

            self.assertEqual([path.name for path in files], ["homework-methods.md"])
            self.assertIn("Question 3", text)
            self.assertIn("Question 7", text)
            self.assertEqual(text.count("## Formula Sheet"), 1)


if __name__ == "__main__":
    unittest.main()
