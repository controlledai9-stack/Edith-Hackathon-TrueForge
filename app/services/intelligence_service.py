"""
Feature 3 — "Ask the Live Web". Grounds answers about recent changes in the
watchlist system's own scraped evidence (snapshots + detected changes)
rather than sending the raw question straight to the model. Falls back to
Tavily for extra context when the local monitored dataset is insufficient.

Grok never scrapes anything itself here — it only reasons over evidence
JARVIS hands it, and is explicitly told to separate verified fact from
inference from unknown.
"""
import logging
import re
from typing import List, Optional

from config import GROQ_API_KEYS, GROQ_MODEL, TAVILY_API_KEY
from app.services.watchlist_service import get_watchlist_service

logger = logging.getLogger("EDITH")

_LIVE_KEYWORDS = [
    "changed", "change", "update", "updated", "latest", "recent", "recently",
    "this week", "today", "new release", "announcement", "pricing change",
]


def needs_live_data(query: str) -> bool:
    q = (query or "").lower()
    return any(k in q for k in _LIVE_KEYWORDS)


def matching_entities(query: str) -> List[dict]:
    q = (query or "").lower()
    watchlist = get_watchlist_service()
    matches = []
    for w in watchlist.get_watchlists():
        if w["name"].lower() in q:
            matches.append(w)
    return matches


def _build_evidence_block(entities: List[dict]) -> str:
    watchlist = get_watchlist_service()
    blocks = []
    for entry in entities:
        for category in entry["categories"]:
            history = watchlist.scraper.get_snapshot_history(entry["name"], category)
            if len(history) < 1:
                continue
            latest = history[-1]
            previous = history[-2] if len(history) >= 2 else None
            blocks.append(
                f"ENTITY: {entry['name']}\nCATEGORY: {category}\n"
                f"SOURCE: {latest.get('source_url')}\n"
                f"LAST SCANNED: {latest.get('timestamp')}\n"
                f"CURRENT DATA: {str(latest.get('data'))[:800]}\n"
                + (f"PREVIOUS DATA: {str(previous.get('data'))[:800]}\nPREVIOUS SCANNED: {previous.get('timestamp')}\n" if previous else "PREVIOUS DATA: (no earlier snapshot yet)\n")
            )
    return "\n---\n".join(blocks)


def _tavily_context(query: str) -> str:
    if not TAVILY_API_KEY:
        return ""
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        resp = client.search(query=query, max_results=4, include_answer=True)
        parts = [resp.get("answer", "")]
        for r in resp.get("results", [])[:4]:
            parts.append(f"- {r.get('title')} ({r.get('url')}): {r.get('content', '')[:300]}")
        return "\n".join(p for p in parts if p)
    except Exception as e:
        logger.warning("[INTELLIGENCE] Tavily context fetch failed: %s", e)
        return ""


_EVIDENCE_SYSTEM_PROMPT = """You are EDITH's live-intelligence layer. You are given verified evidence \
gathered by the monitoring system (structured scrape snapshots and/or web search context) \
about recent changes to tracked entities.

Rules:
- Base your answer ONLY on the evidence provided. Never invent facts, numbers, or dates.
- Clearly separate: Verified fact (directly in the evidence), Analysis/inference (your reasoning \
about what it means), and Unknown (explicitly say so if the evidence doesn't cover something asked).
- If the evidence shows no real change, say plainly that no verified change was detected — do not \
manufacture a change to seem more useful.
- Lead with a plain conclusion, then give only the details needed to support it.
- Mention the source name and date naturally when useful, but do not print raw URLs or append a source list unless the user asks for sources.
- When your answer rests on thin or indirect evidence (a single snapshot with no prior comparison, \
web-search context instead of a direct structured snapshot, or an inference rather than a stated fact), \
end with one line: "Confidence: High/Medium/Low — <short reason>". Omit this line entirely for a \
straightforward, well-supported factual lookup where it would add nothing.
- Plain text only, no markdown formatting."""

_CONFIDENCE_RE = re.compile(r"confidence:\s*(high|medium|low)\b", re.I)


def _extract_confidence(answer: str) -> Optional[str]:
    m = _CONFIDENCE_RE.search(answer or "")
    return m.group(1).capitalize() if m else None


def answer_live_query(query: str) -> dict:
    """Returns {"answer": str, "entities_used": [...], "evidence_found": bool}."""
    entities = matching_entities(query)
    evidence = _build_evidence_block(entities) if entities else ""
    tavily_context = ""

    if not evidence:
        tavily_context = _tavily_context(query)

    if not evidence and not tavily_context:
        return {
            "answer": "I don't have any monitored data or search context to verify that yet — "
                      "add the relevant entity to your watchlist first, or ask me to research it.",
            "entities_used": [], "evidence_found": False,
        }

    if not GROQ_API_KEYS:
        return {
            "answer": "Evidence was found but I can't reach the language model to summarize it "
                      "(GROQ_API_KEY missing).",
            "entities_used": [e["name"] for e in entities], "evidence_found": True,
        }

    try:
        from langchain_groq import ChatGroq
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = ChatGroq(groq_api_key=GROQ_API_KEYS[0], model_name=GROQ_MODEL, temperature=0.2)
        user_content = f"USER QUESTION: {query}\n\n"
        if evidence:
            user_content += f"MONITORED SNAPSHOT EVIDENCE:\n{evidence}\n\n"
        if tavily_context:
            user_content += f"WEB SEARCH CONTEXT (supplementary, not a structured snapshot):\n{tavily_context}\n\n"
        user_content += "Answer the user's question using only the evidence above."

        resp = llm.invoke([SystemMessage(content=_EVIDENCE_SYSTEM_PROMPT), HumanMessage(content=user_content)])
        answer = (resp.content or "").strip()
    except Exception as e:
        logger.error("[INTELLIGENCE] Groq synthesis failed: %s", e)
        answer = "Found relevant evidence but couldn't summarize it — the language model call failed."

    return {
        "answer": answer,
        "entities_used": [e["name"] for e in entities],
        "evidence_found": bool(evidence or tavily_context),
        "used_tavily_fallback": bool(tavily_context and not evidence),
        "confidence": _extract_confidence(answer),
    }


def explain_change(change: dict) -> str:
    """Short evidence-grounded explanation of a single detected change
    record, for the Live Feed's click-to-expand detail view."""
    if not GROQ_API_KEYS:
        return "Can't generate an explanation — GROQ_API_KEY isn't configured."

    evidence = (
        f"ENTITY: {change.get('entity')}\n"
        f"CATEGORY: {change.get('category', 'n/a')}\n"
        f"CHANGE TYPE: {change.get('change_type')}\n"
        f"FIELD: {change.get('field')}\n"
        f"BEFORE: {change.get('before')}\n"
        f"AFTER: {change.get('after')}\n"
        + (f"PERCENTAGE CHANGE: {change.get('percentage_change')}%\n" if change.get("percentage_change") is not None else "")
        + f"SOURCE: {change.get('source_url', 'n/a')}\n"
        f"DETECTED AT: {change.get('detected_at')}\n"
    )
    try:
        from langchain_groq import ChatGroq
        from langchain_core.messages import SystemMessage, HumanMessage
        llm = ChatGroq(groq_api_key=GROQ_API_KEYS[0], model_name=GROQ_MODEL, temperature=0.2)
        resp = llm.invoke([
            SystemMessage(content=_EVIDENCE_SYSTEM_PROMPT),
            HumanMessage(content=f"Explain the likely significance of this detected change, using only the evidence given:\n\n{evidence}"),
        ])
        return (resp.content or "").strip()
    except Exception as e:
        logger.error("[INTELLIGENCE] explain_change failed: %s", e)
        return "Couldn't generate an explanation for this change right now."


def compare_entities(name_a: str, name_b: str) -> dict:
    """Builds a structured side-by-side comparison of two watchlist entities
    across whatever categories they share snapshot data for, plus a short
    narrative summary. Returns a dict with a 'rows' table the UI can render
    directly, and a 'narrative' string for chat display (rendered as a
    plain-text aligned table, since chat is text-only)."""
    watchlist = get_watchlist_service()
    entry_a = watchlist.get_watchlist(name_a)
    entry_b = watchlist.get_watchlist(name_b)

    if not entry_a or not entry_b:
        missing = name_a if not entry_a else name_b
        return {
            "entity_a": name_a, "entity_b": name_b, "rows": [],
            "narrative": f"'{missing}' isn't on your watchlist yet — add it first "
                         f"('Monitor {missing}') so there's evidence to compare.",
        }

    shared_categories = [c for c in entry_a["categories"] if c in entry_b["categories"]]
    if not shared_categories:
        return {
            "entity_a": entry_a["name"], "entity_b": entry_b["name"], "rows": [],
            "narrative": f"{entry_a['name']} and {entry_b['name']} don't share any monitored "
                         f"categories yet, so there's nothing structured to compare — "
                         f"try monitoring the same category for both.",
        }

    rows = []
    for category in shared_categories:
        snap_a = watchlist.scraper.get_latest_snapshot(entry_a["name"], category)
        snap_b = watchlist.scraper.get_latest_snapshot(entry_b["name"], category)
        rows.append({
            "category": category,
            "a_value": str(snap_a.get("data"))[:300] if snap_a else "(no snapshot yet)",
            "a_scanned": snap_a.get("timestamp") if snap_a else None,
            "b_value": str(snap_b.get("data"))[:300] if snap_b else "(no snapshot yet)",
            "b_scanned": snap_b.get("timestamp") if snap_b else None,
        })

    narrative_lines = [f"Comparing {entry_a['name']} vs {entry_b['name']}:\n"]
    for r in rows:
        narrative_lines.append(f"[{r['category']}]")
        narrative_lines.append(f"  {entry_a['name']}: {r['a_value']}")
        narrative_lines.append(f"  {entry_b['name']}: {r['b_value']}")
        narrative_lines.append("")
    narrative = "\n".join(narrative_lines).strip()

    return {
        "entity_a": entry_a["name"], "entity_b": entry_b["name"],
        "rows": rows, "narrative": narrative,
    }
