from __future__ import annotations

from typing import Any

from config import GROQ_API_KEY, GROQ_VISION_MODEL, TRUEFORGE_AGENT_PROFILES, TRUEFORGE_CODE_SANDBOX_ENABLED, TRUEFORGE_MCP_NAME, TRUEFORGE_MODEL
from app.integrations.trueforge.client import TrueForgeClient


PROFILE_INSTRUCTIONS = {
    "general": """You are EDITH in General mode. Be concise, helpful, and honest. Use memory and read-only tools when useful. Use tools only when they materially improve the answer. Never claim an action completed unless a tool result confirms it. Default local-service, postal, delivery, shopping, price, availability, regulation, and consumer answers to India unless the user names another place. Respect explicitly global or foreign scopes.""",
    "research": """You are EDITH in Research mode. Plan evidence-based research, use web/document/memory tools, keep sources attributable, and synthesize conclusions. For homework, show clean student-friendly working but never expose hidden reasoning or scratchpad. Ask for a clearer image when evidence is unreadable. Default local-market and local-service research to India unless another region or a global scope is requested.""",
    "code": """You are EDITH in Code mode. Inspect before editing, make focused changes, use the sandbox for commands and tests, preserve unrelated work, and report verification honestly. Never run destructive operations without explicit approval.""",
    "work": """You are EDITH in Work mode. Break complex goals into verifiable steps and combine EDITH MCP tools to create artifacts or perform connected work. If the user explicitly asks you to ask a question first, call ask_user_question before discovering or running any MCP tool. Prefer direct MCP tools such as create_document and create_pdf. When the user explicitly asks for a one-page PDF, pass one_page=true to create_pdf and keep the content concise enough to remain legible. For other capabilities, query capability_catalog once with one or two keywords, use the exact returned capability name with capability_schema, then call its execute_with adapter. Never call get_tool_info for an inner EDITH capability and never repeat an empty catalog search more than once. Read-only steps may run autonomously. Publishing, sending, uploading, deleting, purchases, account changes, and other consequential actions must pause for user approval. Never treat a confirmation ID as a filename. Default local services, deliveries, shopping, prices, availability, and regulations to India unless another region or a global scope is requested.""",
}


def build_manifest(profile: str) -> dict[str, Any]:
    if not TRUEFORGE_MODEL:
        raise ValueError("TRUEFORGE_MODEL must name a model configured in TrueForge (for example, groq/openai/gpt-oss-120b).")
    is_code = profile == "code"
    max_tokens = 4096 if profile in {"research", "code"} else 2048
    approval_tools = ["work_execute", "browser_execute", "create_document", "create_pdf"] if profile == "work" else []
    return {
        "model": {"name": TRUEFORGE_MODEL, "params": {
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "include_reasoning": False,
        }},
        "instructions": PROFILE_INSTRUCTIONS[profile],
        "mcp_servers": [{
            "name": TRUEFORGE_MCP_NAME,
            "enable_tools": ["@all"],
            "preload": False,
            "preload_tools": ["memory_search"] if profile == "general" else [],
            "require_approval_for_tools": approval_tools,
        }],
        "config": {
            "sandbox": {"enabled": is_code and TRUEFORGE_CODE_SANDBOX_ENABLED, "file_downloads": True},
            "generative_ui": {"enabled": True},
            "ask_user_questions": {"enabled": True},
            "dynamic_sub_agents": {"enabled": profile == "research"},
            "context_management": {
                "compaction": {"enabled": True},
                "large_tool_response": {"enabled": True},
            },
            "iteration_limit": 16,
        },
        "response_format": {"type": "text"},
    }


async def bootstrap_trueforge(client: TrueForgeClient, mcp_url: str) -> dict[str, Any]:
    from config import TRUEFORGE_MCP_NAME

    provider = None
    if GROQ_API_KEY and TRUEFORGE_MODEL.startswith("groq/"):
        provider = await client.upsert_openai_compatible_provider(
            name="groq",
            base_url="https://api.groq.com/openai/v1",
            api_key=GROQ_API_KEY,
            model_id=GROQ_VISION_MODEL,
            model_name=TRUEFORGE_MODEL.split("/", 1)[1],
        )
    connector = await client.upsert_mcp_server(
        TRUEFORGE_MCP_NAME,
        mcp_url,
        "Local EDITH capabilities: memory, research, files, artifacts, browser, and connected Work Mode plugins.",
    )
    existing = {str(item.get("name")): item for item in await client.list_agents()}
    results = []
    for profile, name in TRUEFORGE_AGENT_PROFILES.items():
        manifest = build_manifest(profile)
        current = existing.get(name)
        if current and current.get("id"):
            saved = await client.update_agent(str(current["id"]), manifest)
            action = "updated"
        else:
            saved = await client.create_agent(name, manifest)
            action = "created"
        results.append({"profile": profile, "name": name, "action": action, "id": saved.get("id")})
    return {"provider": provider, "connector": connector, "agents": results}
