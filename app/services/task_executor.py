import logging
import urllib.parse
from typing import List, Tuple, Dict, Any

from app.services.decision_types import (
    INTENT_OPEN, INTENT_PLAY, INTENT_GENERATE_IMAGE, INTENT_CONTENT,
    INTENT_GOOGLE_SEARCH, INTENT_YOUTUBE_SEARCH,
    INTENT_OPEN_WEBCAM, INTENT_CLOSE_WEBCAM,
    INSTANT_INTENTS, BACKGROUND_INTENTS,
)

logger = logging.getLogger("J.A.R.V.I.S")


def _youtube_search_url(query: str) -> str:
    return "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)


def _google_search_url(query: str) -> str:
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)


def build_actions_and_background(intents: List[Tuple[str, dict]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Given (intent_key, payload) pairs from the Brain, split them into
    actions the frontend can execute immediately vs. jobs to run in the
    background (image generation / content writing).

    Returns (actions_dict, background_job_specs)
    """
    actions: Dict[str, Any] = {
        "wopens": [], "plays": [], "googlesearches": [], "youtubesearches": [],
        "images": [], "contents": [], "cam": None,
    }
    background_jobs: List[Dict[str, Any]] = []

    for intent, payload in intents:
        if intent == INTENT_OPEN and intent in INSTANT_INTENTS:
            url = payload.get("url") or "https://www.google.com"
            actions["wopens"].append(url)

        elif intent == INTENT_PLAY:
            query = payload.get("query") or payload.get("message", "")
            actions["plays"].append(_youtube_search_url(query))

        elif intent == INTENT_GOOGLE_SEARCH:
            query = payload.get("query") or payload.get("message", "")
            actions["googlesearches"].append(_google_search_url(query))

        elif intent == INTENT_YOUTUBE_SEARCH:
            query = payload.get("query") or payload.get("message", "")
            actions["youtubesearches"].append(_youtube_search_url(query))

        elif intent == INTENT_OPEN_WEBCAM:
            actions["cam"] = {"action": "open"}

        elif intent == INTENT_CLOSE_WEBCAM:
            actions["cam"] = {"action": "close"}

        elif intent == INTENT_GENERATE_IMAGE:
            prompt = payload.get("prompt") or payload.get("message", "")
            background_jobs.append({"type": "generate image", "prompt": prompt, "label": prompt[:60]})

        elif intent == INTENT_CONTENT:
            prompt = payload.get("prompt") or payload.get("message", "")
            background_jobs.append({"type": "content", "prompt": prompt, "label": prompt[:60]})

    # Drop empty lists so the frontend doesn't render blank sections.
    actions = {k: v for k, v in actions.items() if v}
    return actions, background_jobs


def generate_image_url(prompt: str) -> str:
    """Free, keyless image generation via Pollinations.ai."""
    encoded = urllib.parse.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true"


def generate_content_text(prompt: str) -> str:
    """Synchronous content-writing call used by the background task worker."""
    from config import GROQ_API_KEYS, GROQ_MODEL

    if not GROQ_API_KEYS:
        return "Content generation isn't available — no GROQ_API_KEY configured."

    try:
        from langchain_groq import ChatGroq
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = ChatGroq(groq_api_key=GROQ_API_KEYS[0], model_name=GROQ_MODEL, temperature=0.7)
        system = (
            "You are a skilled writer. Produce clean, well-structured, ready-to-use "
            "written content for the user's request — no meta-commentary, no "
            "'here is your content' preamble, just the content itself."
        )
        resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=prompt)])
        return (resp.content or "").strip()
    except Exception as e:
        logger.error("[TASK] Content generation failed: %s", e)
        return f"Sorry, content generation failed: {e}"
