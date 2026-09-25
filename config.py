import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

_storage_root = os.getenv("EDITH_STORAGE_ROOT", "").strip()
STORAGE_ROOT = Path(_storage_root).expanduser() if _storage_root else BASE_DIR

LEARNING_DATA_DIR = STORAGE_ROOT / "database" / "learning_data"
CHATS_DATA_DIR = STORAGE_ROOT / "database" / "chats_data"
VECTOR_STORE_DIR = STORAGE_ROOT / "database" / "vector_store"
CAMERA_CAPTURES_DIR = STORAGE_ROOT / "database" / "camera_captures"

DATA_DIR = STORAGE_ROOT / "data"
WATCHLISTS_FILE = DATA_DIR / "watchlists.json"
SCRAPER_HEALTH_FILE = DATA_DIR / "scraper_health.json"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
CHANGES_DIR = DATA_DIR / "changes"
MONITORING_HISTORY_DIR = DATA_DIR / "monitoring_history"
RESEARCH_MISSIONS_DIR = DATA_DIR / "research_missions"
RESEARCH_MODE_DIR = DATA_DIR / "research_mode"
TRUEFORGE_DATA_DIR = DATA_DIR / "trueforge"

LEARNING_DATA_DIR.mkdir(parents=True, exist_ok=True)
CHATS_DATA_DIR.mkdir(parents=True, exist_ok=True)
VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
CAMERA_CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
CHANGES_DIR.mkdir(parents=True, exist_ok=True)
MONITORING_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
RESEARCH_MISSIONS_DIR.mkdir(parents=True, exist_ok=True)
RESEARCH_MODE_DIR.mkdir(parents=True, exist_ok=True)
TRUEFORGE_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# TrueForge is the primary harness when enabled.  The legacy EDITH pipelines
# remain available as an explicit, observable fallback while migrating.
TRUEFORGE_ENABLED = _env_bool("TRUEFORGE_ENABLED", True)
TRUEFORGE_FALLBACK_ENABLED = _env_bool("TRUEFORGE_FALLBACK_ENABLED", True)
TRUEFORGE_AUTO_BOOTSTRAP = _env_bool("TRUEFORGE_AUTO_BOOTSTRAP", False)
TRUEFORGE_CODE_SANDBOX_ENABLED = _env_bool("TRUEFORGE_CODE_SANDBOX_ENABLED", os.name != "nt")
TRUEFORGE_BASE_URL = os.getenv("TRUEFORGE_BASE_URL", "http://localhost:8790").strip().rstrip("/")
TRUEFORGE_TOKEN = os.getenv("TRUEFORGE_TOKEN", "").strip()
TRUEFORGE_TIMEOUT_SECONDS = float(os.getenv("TRUEFORGE_TIMEOUT_SECONDS", "600"))
TRUEFORGE_MODEL = os.getenv("TRUEFORGE_MODEL", "groq/qwen3-6-27b").strip()
TRUEFORGE_MCP_NAME = os.getenv("TRUEFORGE_MCP_NAME", "edith-core").strip() or "edith-core"
TRUEFORGE_MCP_URL = os.getenv("TRUEFORGE_MCP_URL", "http://127.0.0.1:8000/mcp/").strip()
TRUEFORGE_SESSION_MAP = TRUEFORGE_DATA_DIR / "session_map.json"
TRUEFORGE_AGENT_PROFILES = {
    "general": os.getenv("TRUEFORGE_AGENT_GENERAL", "edith-general").strip() or "edith-general",
    "research": os.getenv("TRUEFORGE_AGENT_RESEARCH", "edith-research").strip() or "edith-research",
    "code": os.getenv("TRUEFORGE_AGENT_CODE", "edith-code").strip() or "edith-code",
    "work": os.getenv("TRUEFORGE_AGENT_WORK", "edith-work").strip() or "edith-work",
}

def _load_groq_api_keys() -> list:
    keys = []

    first = os.getenv("GROQ_API_KEY", "").strip()
    if first:
        keys.append(first)

    i = 2

    while True:
        k = os.getenv(f"GROQ_API_KEY_{i}", "").strip()

        if not k:
            break

        keys.append(k)
        i += 1

    return keys

GROQ_API_KEYS = _load_groq_api_keys()
GROQ_API_KEY = GROQ_API_KEYS[0] if GROQ_API_KEYS else ""
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
GROQ_BRAIN_MODEL = os.getenv("GROQ_BRAIN_MODEL", "openai/gpt-oss-20b")
INTENT_CLASSIFY_MODEL = os.getenv("INTENT_CLASSIFY_MODEL", "openai/gpt-oss-20b")
TASK_EXECUTION_TIMEOUT = int(os.getenv("TASK_EXECUTION_TIMEOUT", "30"))
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")
GROQ_HOMEWORK_MODEL = os.getenv("GROQ_HOMEWORK_MODEL", "qwen/qwen3.6-27b").strip() or "qwen/qwen3.6-27b"
VISION_MAX_IMAGE_BYTES = int(os.getenv("VISION_MAX_IMAGE_BYTES", "5000000"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-3.1-pro-preview").strip() or "gemini-3.1-pro-preview"
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image").strip() or "gemini-3.1-flash-image"
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip() or "openrouter/free"
MODEL_PROVIDER_ORDER = os.getenv("MODEL_PROVIDER_ORDER", "groq,gemini,openrouter").strip() or "groq,gemini,openrouter"
TTS_VOICE = os.getenv("TTS_VOICE", "en-GB-RyanNeural")
TTS_RATE = os.getenv("TTS_RATE", "+14%")
TTS_PITCH = os.getenv("TTS_PITCH", "+8Hz")
TTS_VOLUME = os.getenv("TTS_VOLUME", "+0%")

def _clean_env(name: str) -> str:
    """Read an env var and strip an accidentally-pasted 'NAME=' prefix from
    its own value (for example, a pasted NAME=value string)
    instead of just 'abc123' because a whole KEY=value line got pasted as
    the value). Defensive against copy-paste mistakes in .env."""
    raw = os.getenv(name, "").strip()
    prefix = name + "="
    while raw.upper().startswith(prefix.upper()):
        raw = raw[len(prefix):].strip()
    return raw


EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
ENABLE_VECTOR_MEMORY = os.getenv("ENABLE_VECTOR_MEMORY", "true").strip().lower() in {"1", "true", "yes", "on"}
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
MAX_CHAT_HISTORY_TURNS = 10
MAX_MESSAGE_LENGTH = 32_000
SESSION_CONTEXT_TOKEN_BUDGET = int(os.getenv("SESSION_CONTEXT_TOKEN_BUDGET", "2200"))
SESSION_RECENT_TOKEN_BUDGET = int(os.getenv("SESSION_RECENT_TOKEN_BUDGET", "1450"))
SESSION_SUMMARY_TOKEN_BUDGET = int(os.getenv("SESSION_SUMMARY_TOKEN_BUDGET", "650"))
SOURCE_CHUNK_TOKEN_SIZE = int(os.getenv("SOURCE_CHUNK_TOKEN_SIZE", "650"))
SOURCE_CHUNK_TOKEN_OVERLAP = int(os.getenv("SOURCE_CHUNK_TOKEN_OVERLAP", "80"))
SOURCE_CONTEXT_TOKEN_BUDGET = int(os.getenv("SOURCE_CONTEXT_TOKEN_BUDGET", "3200"))
RESEARCH_EVIDENCE_TOKEN_BUDGET = int(os.getenv("RESEARCH_EVIDENCE_TOKEN_BUDGET", "5200"))
EDIT_MEMORY_TOKEN_BUDGET = int(os.getenv("EDIT_MEMORY_TOKEN_BUDGET", "700"))
EDIT_STATIC_CONTEXT_TOKEN_BUDGET = int(os.getenv("EDIT_STATIC_CONTEXT_TOKEN_BUDGET", "700"))
EDIT_OUTPUT_TOKEN_BUDGET = int(os.getenv("EDIT_OUTPUT_TOKEN_BUDGET", "900"))
RESEARCH_OUTPUT_TOKEN_BUDGET = int(os.getenv("RESEARCH_OUTPUT_TOKEN_BUDGET", "1400"))
HOMEWORK_OUTPUT_TOKEN_BUDGET = int(os.getenv("HOMEWORK_OUTPUT_TOKEN_BUDGET", "2600"))
ASSISTANT_NAME = (os.getenv("ASSISTANT_NAME", "").strip() or "Edith")
DEFAULT_REGION = (os.getenv("DEFAULT_REGION", "").strip() or "India")
JARVIS_USER_TITLE = os.getenv("JARVIS_USER_TITLE", "").strip()
JARVIS_OWNER_NAME = os.getenv("JARVIS_OWNER_NAME", "").strip()

_JARVIS_SYSTEM_PROMPT_BASE = """You are {assistant_name}, a complete AI assistant. You help with information, tasks, and actions. Sharp, warm, a little witty. Keep language simple and natural.

You know the user's personal information and past conversations. Use this when relevant but never reveal the source.

=== ROLE ===
The user can ask you anything or ask you to do things (open, generate, play, write, search). The backend carries out actions; you respond in words. Only say something is done if the result is visible; otherwise say you are doing it.

=== CAN DO ===
Answer questions, open websites/apps, play music/videos, generate images, write content (essays, poems, code, emails), search Google/YouTube, analyze camera images (you CAN see what the user shows).

=== CANNOT DO (be honest) ===
Read emails, control smart home, run code, send messages, make purchases, access files, make calls. Say clearly: "I can't do that."
Never pretend you can do something you cannot. Never hallucinate URLs, numbers, or data.

=== HONESTY ===
If reliable evidence is unavailable, describe the evidence gap precisely instead of saying only "I don't know" or "I'm not sure." For public facts, say that no reliable public source or disclosed figure was found for the requested scope and date. Never fabricate facts.

=== USER INTENT ===
Understand what the user actually wants. Use conversation history for ambiguous messages. If corrected, acknowledge briefly and fix it. Resolve follow-ups like "that one" / "no, I meant..." from context.

=== DEFAULT REGION ===
The user's default region is India. For local services, post offices, deliveries, shopping, prices, currency, availability, regulations, dates, and consumer guidance, answer for India unless the user names another country. For worldwide comparisons, global rankings, international topics, or a specifically named country/market, use the requested scope instead. Never force an India framing onto a clearly global question.

=== LENGTH — CRITICAL ===
Reply SHORT by default (1-2 sentences). Only elaborate when explicitly asked or question demands it. No intros, no wrap-ups.

=== QUALITY ===
Be accurate and specific. Use concrete facts, names, numbers. Give actionable answers. One sharp sentence beats a paragraph.

=== STYLE ===
Warm, intelligent, brief. Match the user's energy. Address user by name if known. No asterisks, no emojis, no markdown. Standard punctuation only.

=== ANTI-REPETITION ===
State each fact ONCE. Never repeat the same point. "A, B, and C." — not "A and also B and also C."
"""


_JARVIS_SYSTEM_PROMPT_BASE_FMT = _JARVIS_SYSTEM_PROMPT_BASE.format(assistant_name=ASSISTANT_NAME)

if JARVIS_USER_TITLE:
    JARVIS_SYSTEM_PROMPT = _JARVIS_SYSTEM_PROMPT_BASE_FMT + f"\n- When appropriate, you may address the user as: {JARVIS_USER_TITLE}"

else:
    JARVIS_SYSTEM_PROMPT = _JARVIS_SYSTEM_PROMPT_BASE_FMT

GENERAL_CHAT_ADDENDUM = """
You are in GENERAL mode (no web search). Answer from your knowledge and the context provided (learning data, conversation history). Answer confidently and briefly. Never tell the user to search online or check a website — you are their source. Default to 1-2 sentences; only elaborate when the user asks for more or the question clearly needs it. If you have relevant context from the user's learning data, use it naturally without mentioning the source.
"""

REALTIME_CHAT_ADDENDUM = """
You are in REALTIME mode. Live web search results are above.

CRITICAL: Use search results as your PRIMARY source. Extract specific facts, names, numbers, scores, dates. Be concrete.
- If search results contain the answer, USE IT. Do not say "I don't have that information" when the data is right there.
- For sports scores/matches: look for team names, scores, match status in the results. Report what you find.
- Never mention searching or being in realtime mode. Answer naturally.
- If results don't have the exact answer, say what you found. Never refuse when data exists.
- Cross-reference sources. Prefer higher-relevance ones.
- Lead with the conclusion, then give only the details needed to support it.
- Do not narrate source names (for example, "Claude says") or append raw URLs/source lists unless the user explicitly asks for sources. Synthesize the evidence into one professional answer.

LENGTH: 1-2 sentences for simple questions. Only longer when asked.
"""

def load_user_context() -> str:
    context_parts = []

    text_files = sorted(LEARNING_DATA_DIR.glob("*.txt"))

    for file_path in text_files:

        try:

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()

                if content:
                    context_parts.append(content)
                    
        except Exception as e:
            logger.warning("Could not load learning data file %s: %s", file_path, e)

    return "\n\n".join(context_parts) if context_parts else ""
