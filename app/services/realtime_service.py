import logging
import config
from typing import AsyncGenerator, List, Tuple, Optional, Dict, Any

from config import (
    GROQ_API_KEYS, GROQ_MODEL, GROQ_BRAIN_MODEL, TAVILY_API_KEY,
    JARVIS_SYSTEM_PROMPT, REALTIME_CHAT_ADDENDUM,
)
from app.utils.time_info import current_time_context
from app.services.model_router import get_model_router

logger = logging.getLogger("J.A.R.V.I.S")


class RealtimeService:
    def __init__(self):
        self._llms = []
        self._query_llms = []
        self._tavily = None

        if GROQ_API_KEYS:
            try:
                from langchain_groq import ChatGroq
                self._llms = [
                    ChatGroq(groq_api_key=key, model_name=GROQ_MODEL, temperature=0.4, streaming=True)
                    for key in GROQ_API_KEYS
                ]
                self._query_llms = [
                    ChatGroq(groq_api_key=key, model_name=GROQ_BRAIN_MODEL, temperature=0.0, max_tokens=60)
                    for key in GROQ_API_KEYS
                ]
            except Exception as e:
                logger.error("[REALTIME] Failed to initialize Groq model(s): %s", e)

        if TAVILY_API_KEY:
            try:
                from tavily import TavilyClient
                self._tavily = TavilyClient(api_key=TAVILY_API_KEY)
            except Exception as e:
                logger.warning("[REALTIME] Tavily unavailable: %s", e)

    def extract_query(self, user_message: str, chat_history: Optional[List[Tuple[str, str]]], key_index: int = 0) -> str:
        """Turn a conversational message into a clean search query."""
        if not self._query_llms:
            return user_message

        history_text = ""
        if chat_history:
            for u, a in chat_history[-3:]:
                history_text += f"User: {u}\nAssistant: {a}\n"

        prompt = (
            "Rewrite the user's latest message as a short, clean web search query. "
            "Resolve pronouns/follow-ups using the conversation. Output ONLY the query text.\n\n"
            f"Conversation:\n{history_text}\nLatest message: {user_message}\nSearch query:"
        )
        try:
            from langchain_core.messages import HumanMessage
            llm = self._query_llms[key_index % len(self._query_llms)]
            resp = llm.invoke([HumanMessage(content=prompt)])
            query = (resp.content or "").strip().strip('"')
            return query or user_message
        except Exception as e:
            logger.warning("[REALTIME] Query extraction failed, using raw message: %s", e)
            return user_message

    def search(self, query: str, max_results: int = 5, detailed: bool = False) -> Dict[str, Any]:
        if not self._tavily:
            return {"query": query, "answer": "", "results": []}
        try:
            options = {
                "query": query, "max_results": max_results, "include_answer": True,
            }
            if detailed:
                options.update(search_depth="advanced", include_raw_content="text")
            resp = self._tavily.search(**options)
            return {
                "query": query,
                "answer": resp.get("answer", "") or "",
                "results": [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "content": ((r.get("raw_content") if detailed else None)
                                    or r.get("content", ""))[:40000],
                        "score": r.get("score"),
                    }
                    for r in resp.get("results", [])
                ],
            }
        except Exception as e:
            logger.warning("[REALTIME] Tavily search failed: %s", e)
            return {"query": query, "answer": "", "results": []}

    def _build_system_prompt(self, search_payload: Dict[str, Any]) -> str:
        results_text = f"Search answer: {search_payload.get('answer', '')}\n\n"
        for r in search_payload.get("results", []):
            results_text += f"- {r.get('title')} ({r.get('url')}): {r.get('content', '')[:400]}\n"
        return "\n\n".join([
            JARVIS_SYSTEM_PROMPT,
            REALTIME_CHAT_ADDENDUM,
            (
                "EVIDENCE-GAP LANGUAGE: If these results do not establish the requested fact, do not answer with "
                "a bare 'I don't know' or 'I'm not sure.' Say clearly that you could not find a reliable public "
                "source or publicly disclosed figure for the requested person, period, and category. Mention what "
                "kind of disclosure would be needed to verify it. Never infer a number from unrelated figures."
            ),
            current_time_context(),
            f"=== LIVE SEARCH RESULTS ===\n{results_text}",
        ])

    async def stream_reply(
        self,
        user_message: str,
        search_payload: Dict[str, Any],
        chat_history: Optional[List[Tuple[str, str]]] = None,
        key_index: int = 0,
        model_preference: str = "auto",
    ) -> AsyncGenerator[str, None]:
        router = get_model_router()
        if not router.available:
            yield "I can't reach a language model right now — add a Groq, Gemini, or OpenRouter key in Settings."
            return

        system_prompt = self._build_system_prompt(search_payload)
        messages = [{"role": "system", "content": system_prompt}]
        for u, a in (chat_history or []):
            messages.append({"role": "user", "content": u})
            messages.append({"role": "assistant", "content": a})
        messages.append({"role": "user", "content": user_message})

        try:
            async for text in router.astream(
                messages, model=config.GROQ_MODEL, temperature=0.4, preference=model_preference,
                max_tokens=config.EDIT_OUTPUT_TOKEN_BUDGET,
            ):
                if text:
                    yield text
        except Exception as e:
            logger.error("[REALTIME] Streaming failed: %s", e)
            yield "Something went wrong searching for that. Please try again."


_realtime_service_singleton = None


def get_realtime_service() -> RealtimeService:
    global _realtime_service_singleton
    if _realtime_service_singleton is None:
        _realtime_service_singleton = RealtimeService()
    return _realtime_service_singleton
