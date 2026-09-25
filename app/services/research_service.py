"""
Feature 5 — Autonomous Research Missions. Given a high-level goal, runs a
short pipeline: Tavily discovers relevant sources, the direct reader reads the
most promising ones (with self-healing), and Groq synthesizes the findings
into a report that distinguishes verified fact from inference.

Runs on a background thread so the UI can poll status/progress rather than
block a chat turn on a multi-step, multi-minute research job.
"""
import json
import logging
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

import config
from config import RESEARCH_MISSIONS_DIR, TAVILY_API_KEY
from app.services.web_reader_service import get_web_reader_service
from app.services.model_router import get_model_router
from app.services.context_budget import count_tokens, fit_sections, truncate_tokens

logger = logging.getLogger("EDITH")

_MAX_SOURCES_TO_SCRAPE = 6


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_REPORT_SYSTEM_PROMPT = """You are EDITH's research-mission report writer. You are given a research \
goal plus structured/text evidence gathered from real web sources. Write a concise findings report.

Rules:
- Base findings ONLY on the provided evidence. Never invent sources, numbers, or facts.
- Structure the report with short sections: Summary, Key Findings, Uncertainties, Sources.
- Distinguish Verified fact vs Analysis/inference vs Unknown where relevant.
- Cite factual claims using the numbered source marker supplied with each excerpt, such as [1].
- Use readable Markdown but no tables and no chain-of-thought — just the final report."""


class ResearchMissionService:
    def __init__(self, max_workers: int = 2):
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        self.web_reader = get_web_reader_service()

    def _path(self, mission_id: str) -> Path:
        return RESEARCH_MISSIONS_DIR / f"{mission_id}.json"

    def _save(self, mission: dict):
        with self._lock:
            try:
                self._path(mission["mission_id"]).write_text(
                    json.dumps(mission, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception as e:
                logger.warning("[RESEARCH] Could not persist mission %s: %s", mission["mission_id"], e)

    def get_mission(self, mission_id: str) -> Optional[dict]:
        path = self._path(mission_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def list_missions(self, limit: int = 30) -> List[dict]:
        files = sorted(RESEARCH_MISSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
        out = []
        for f in files:
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                continue
        return out

    def start_mission(self, query: str) -> dict:
        mission = {
            "mission_id": uuid.uuid4().hex[:12],
            "query": query,
            "status": "running",
            "current_step": "Discovering sources...",
            "steps": [],
            "sources": [],
            "structured_results": [],
            "findings": "",
            "started_at": _now_iso(),
            "completed_at": None,
        }
        self._save(mission)
        self._pool.submit(self._run_mission, mission["mission_id"], query)
        return mission

    def _update(self, mission_id: str, **fields):
        mission = self.get_mission(mission_id)
        if not mission:
            return
        mission.update(fields)
        self._save(mission)

    def _append_step(self, mission_id: str, step: str):
        mission = self.get_mission(mission_id)
        if not mission:
            return
        mission["steps"].append({"label": step, "at": _now_iso()})
        mission["current_step"] = step
        self._save(mission)

    def _discover_sources(self, query: str):
        if not TAVILY_API_KEY:
            return [], ""
        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=TAVILY_API_KEY)
            resp = client.search(query=query, max_results=_MAX_SOURCES_TO_SCRAPE, include_answer=True)
            sources = [{"title": r.get("title"), "url": r.get("url")} for r in resp.get("results", [])]
            return sources, resp.get("answer", "")
        except Exception as e:
            logger.warning("[RESEARCH] Tavily discovery failed: %s", e)
            return [], ""

    def _plan_queries(self, query: str, model_preference: str = "auto") -> List[str]:
        """Create a small editable-style plan without spending tokens on every page."""
        router = get_model_router()
        if not router.available:
            return [query]
        try:
            raw = router.complete(
                "You plan web research. Return JSON only with a `queries` array containing 2 to 4 concise, non-overlapping search queries. Include the user's region when locally relevant. Do not answer the question.",
                query,
                model=config.GROQ_MODEL,
                temperature=0.1,
                response_format={"type": "json_object"},
                preference=model_preference,
                max_tokens=180,
            )
            values = json.loads(raw).get("queries") or []
            planned = [str(value).strip() for value in values if str(value).strip()]
            return list(dict.fromkeys([query, *planned]))[:4]
        except Exception as exc:
            logger.warning("[RESEARCH] Query planning failed: %s", exc)
            return [query]

    @staticmethod
    def _relevant_excerpt(text: str, query: str, max_tokens: int = 650) -> str:
        body = str(text or "").strip()
        if count_tokens(body) <= max_tokens:
            return body
        terms = set(re.findall(r"[a-z0-9]{3,}", query.lower()))
        passages = [item.strip() for item in re.split(r"\n{2,}|(?<=[.!?])\s+(?=[A-Z0-9])", body) if item.strip()]
        scored = sorted(
            ((sum(part.lower().count(term) for term in terms), -index, part) for index, part in enumerate(passages)),
            reverse=True,
        )
        chosen = []
        used = 0
        for _, _, passage in scored:
            passage_tokens = count_tokens(passage)
            if used + passage_tokens > max_tokens and chosen:
                continue
            chosen.append(truncate_tokens(passage, max_tokens - used))
            used += passage_tokens
            if used >= max_tokens:
                break
        return truncate_tokens(" ".join(chosen), max_tokens)

    def _run_mission(self, mission_id: str, query: str):
        try:
            self._append_step(mission_id, "Discovering sources...")
            sources, tavily_answer = self._discover_sources(query)
            self._update(mission_id, sources=sources)

            if not sources:
                self._update(
                    mission_id, status="completed", completed_at=_now_iso(),
                    findings="No sources could be discovered for this research goal — "
                             "check that TAVILY_API_KEY is configured.",
                )
                return

            self._append_step(mission_id, "Scraping relevant pages...")
            structured_results = []
            for src in sources[:_MAX_SOURCES_TO_SCRAPE]:
                url = src.get("url")
                if not url:
                    continue
                result = self.web_reader.scrape_with_self_healing(url)
                structured_results.append({
                    "url": url, "title": src.get("title"),
                    "success": result.success, "source": result.source,
                    "healed": result.healed,
                    "data": result.data if result.success and result.source == "scraper_studio" else None,
                    "text": (result.text or "")[:1500] if result.success else "",
                    "error": result.error,
                })
            self._update(mission_id, structured_results=structured_results)

            self._append_step(mission_id, "Comparing structured records...")
            # (Cross-source comparison is left to the report-writing model —
            # a full pairwise structured diff across arbitrary unrelated
            # sources isn't well-defined the way single-entity snapshot
            # diffing is in the watchlist system.)

            self._append_step(mission_id, "Generating report...")
            findings = self._generate_report(query, tavily_answer, structured_results)

            self._update(mission_id, status="completed", completed_at=_now_iso(), findings=findings)
            self._append_step(mission_id, "Done")

        except Exception as e:
            logger.error("[RESEARCH] Mission %s failed: %s", mission_id, e)
            self._update(mission_id, status="failed", completed_at=_now_iso(), findings=f"Mission failed: {e}")

    def run_once(
        self,
        query: str,
        supplemental_evidence: str = "",
        model_preference: str = "auto",
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict:
        """Run the evidence pipeline synchronously for dedicated Research Mode."""
        def check_cancelled() -> None:
            if cancel_check is not None and cancel_check():
                raise InterruptedError("Research task cancelled")

        check_cancelled()
        plan = self._plan_queries(query, model_preference)
        check_cancelled()
        sources = []
        tavily_answers = []
        seen_urls = set()
        for planned_query in plan:
            check_cancelled()
            found, answer = self._discover_sources(planned_query)
            check_cancelled()
            if answer:
                tavily_answers.append(answer)
            for source in found:
                url = source.get("url")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    sources.append(source)
            if len(sources) >= 8:
                break
        tavily_answer = "\n".join(tavily_answers)[:5000]
        structured_results = []
        for src in sources[:_MAX_SOURCES_TO_SCRAPE]:
            check_cancelled()
            url = src.get("url")
            if not url:
                continue
            result = self.web_reader.scrape_with_self_healing(url)
            check_cancelled()
            structured_results.append({
                "url": url,
                "title": src.get("title"),
                "success": result.success,
                "source": result.source,
                "healed": result.healed,
                "data": result.data if result.success and result.source == "scraper_studio" else None,
                "text": self._relevant_excerpt(result.text or "", query) if result.success else "",
                "error": result.error,
            })
        check_cancelled()
        findings = self._generate_report(query, tavily_answer, structured_results, supplemental_evidence, model_preference)
        check_cancelled()
        return {"query": query, "plan": plan, "sources": sources, "structured_results": structured_results, "findings": findings}

    def _generate_report(self, query: str, tavily_answer: str, structured_results: List[dict], supplemental_evidence: str = "", model_preference: str = "auto") -> str:
        router = get_model_router()
        if not router.available:
            return "Evidence was gathered but no Groq, Gemini, or OpenRouter model is configured to generate the report."
        evidence_lines = [f"RESEARCH GOAL: {query}\n"]
        if tavily_answer:
            evidence_lines.append(f"SEARCH OVERVIEW: {tavily_answer}\n")
        if supplemental_evidence:
            evidence_lines.append(f"USER-PROVIDED VISUAL OR DOCUMENT EVIDENCE:\n{supplemental_evidence[:12000]}\n")
        for index, r in enumerate(structured_results, start=1):
            evidence_lines.append(
                f"SOURCE [{index}]: {r['title']} ({r['url']})\n"
                f"SCRAPE STATUS: {'success via ' + r['source'] if r['success'] else 'failed — ' + str(r['error'])}\n"
                f"CONTENT: {(str(r['data']) if r['data'] else r['text'])[:1800]}\n"
            )
        evidence, _ = fit_sections(
            [(f"RESEARCH MATERIAL {index + 1}:", value) for index, value in enumerate(evidence_lines)],
            config.RESEARCH_EVIDENCE_TOKEN_BUDGET,
        )
        try:
            return router.complete(
                _REPORT_SYSTEM_PROMPT, evidence, model=config.GROQ_MODEL,
                temperature=0.3, preference=model_preference,
                max_tokens=config.RESEARCH_OUTPUT_TOKEN_BUDGET,
            )
        except Exception as e:
            logger.error("[RESEARCH] Report generation failed: %s", e)
            return f"Evidence was gathered from {len(structured_results)} source(s) but report generation failed: {e}"


_research_service_singleton = None


def get_research_service() -> ResearchMissionService:
    global _research_service_singleton
    if _research_service_singleton is None:
        _research_service_singleton = ResearchMissionService()
    return _research_service_singleton
