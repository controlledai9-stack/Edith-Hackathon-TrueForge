import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import config
from app.services.chat_service import ChatService
from app.services.context_budget import chunk_text_tokens, compact_history, count_tokens, fit_sections
from app.services.research_mode_service import ResearchModeService


class TokenBudgetTests(unittest.TestCase):
    def test_token_chunks_respect_size_and_overlap(self):
        text = " ".join(f"Photosynthesis fact {index}." for index in range(900))
        chunks = chunk_text_tokens(text, chunk_tokens=120, overlap_tokens=20)
        self.assertGreater(len(chunks), 5)
        self.assertTrue(all(count_tokens(chunk) <= 125 for chunk in chunks))
        self.assertLess(sum(count_tokens(chunk) for chunk in chunks), count_tokens(text) * 1.3)
        code_chunks = chunk_text_tokens("x" * 20_000, chunk_tokens=120, overlap_tokens=20)
        self.assertGreater(len(code_chunks), 5)
        self.assertTrue(all(count_tokens(chunk) <= 120 for chunk in code_chunks))

    def test_long_session_becomes_bounded_checkpoint(self):
        turns = [(f"Question {index} " * 30, f"Answer {index} " * 45) for index in range(30)]
        context, stats = compact_history(turns, total_budget=700, recent_budget=430, summary_budget=220)
        self.assertLessEqual(stats["tokens"], 700)
        self.assertGreater(stats["compacted_turns"], 0)
        self.assertIn("Earlier session checkpoint", context[0][1])
        self.assertIn("Question 29", context[-1][0])

    def test_shared_section_budget_never_overflows(self):
        content, stats = fit_sections([("A", "alpha " * 1000), ("B", "beta " * 1000)], 240)
        self.assertLessEqual(count_tokens(content), 240)
        self.assertGreater(stats["saved"], 0)


class SessionCheckpointTests(unittest.TestCase):
    def test_chat_service_persists_checkpoint_metrics(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = ChatService()
            service._path = lambda session_id: Path(temporary) / f"{session_id}.json"
            session = service.new_session()
            for index in range(20):
                service.append_turn(session, f"User request {index} " * 35, f"Assistant response {index} " * 45)
            context = service.get_model_context(session)
            payload = json.loads(service._path(session).read_text(encoding="utf-8"))
            stats = service.get_context_stats(session)
        self.assertTrue(context)
        self.assertIn("context_checkpoint", payload)
        self.assertLessEqual(stats["tokens"], config.SESSION_CONTEXT_TOKEN_BUDGET)
        self.assertGreater(stats["compacted_turns"], 0)


class SessionSourceRetrievalTests(unittest.TestCase):
    def _service(self, root: Path) -> ResearchModeService:
        service = ResearchModeService()
        service.sources_dir = root / "sources"
        service.sources_dir.mkdir()
        service.memory = Mock()
        service.memory.embed_documents.return_value = []
        service.memory.embed_query.return_value = []
        return service

    def test_retrieval_is_session_scoped_budgeted_and_source_controllable(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = self._service(Path(temporary))
            first = service._store_source("session-a", "Biology", "chlorophyll captures sunlight. " * 700, "text")
            service._store_source("session-b", "Private economics", "inflation and interest rates. " * 700, "text")
            context = service._retrieve_source_context("session-a", "How does chlorophyll capture sunlight?", token_budget=500)
            self.assertIn("chlorophyll", context)
            self.assertNotIn("inflation", context)
            self.assertLessEqual(count_tokens(context), 500)
            self.assertGreater(service._last_retrieval_stats["selected_chunks"], 0)

            service.set_source_enabled("session-a", first["source_id"], False)
            self.assertEqual(service._retrieve_source_context("session-a", "chlorophyll", token_budget=500), "")
            self.assertFalse(service.list_sources("session-a")[0]["enabled"])
            self.assertTrue(service.delete_source("session-a", first["source_id"]))
            self.assertEqual(service.list_sources("session-a"), [])


if __name__ == "__main__":
    unittest.main()
