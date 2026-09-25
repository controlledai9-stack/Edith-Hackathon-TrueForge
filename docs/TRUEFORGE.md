# EDITH + TrueForge architecture

EDITH now uses TrueForge 0.1.4 as its primary agent harness. The FastAPI application remains the product boundary: it owns the UI, local chat records, artifacts, OAuth callbacks, and deterministic commands. TrueForge owns agent sessions, multi-step turns, model/tool iteration, context compaction, subagents, sandbox execution, pauses, cancellation, and resumable event streams.

## Runtime topology

- EDITH FastAPI/UI: `http://127.0.0.1:8000`
- EDITH MCP adapter: `http://127.0.0.1:8000/mcp/`
- Local TrueForge: `http://localhost:8790` (v0.1.4 binds the Windows standalone server to IPv6 localhost)
- Session mapping: `data/trueforge/session_map.json`
- TrueForge local state: its standalone SQLite storage under the local runtime

TrueForge 0.1.4 needs two narrow compatibility fixes in this environment: Kysely passes raw Windows drive paths to Node's ESM loader, and TrueForge replays model reasoning blocks to Groq as unsupported assistant `reasoning_content` during tool loops. `trueforge/scripts/patch-kysely-windows.mjs` applies the Windows `file://` conversion and suppresses only Groq reasoning-history replay after every install. Reasoning is never shown in EDITH. These pinned-runtime patches can be removed once upstream includes equivalent fixes.

Local TrueForge has no login by default. Keep both services bound to localhost. Do not expose port 8790 to a LAN or the public internet without enabling TrueForge OIDC and normal production hardening.

## Request routing

Direct, deterministic commands such as opening a URL, a known local task/reminder command, watchlist operations, and the existing scrape path stay in FastAPI. General conversation and agentic work route to one of four TrueForge profiles:

- `edith-general`: concise conversation plus memory and read-only tools.
- `edith-research`: evidence gathering, synthesis, vision/file inputs, and optional parallel subagents.
- `edith-code`: sandbox-enabled coding and verification.
- `edith-work`: artifact and connected-service workflows, with `work_execute` and `browser_execute` approval-gated.

If the feature flag is enabled but TrueForge is unavailable, EDITH emits a visible `harness_fallback` activity and uses the existing pipeline when `TRUEFORGE_FALLBACK_ENABLED=true`. It never silently switches engines.

TrueForge's built-in local sandbox reports macOS/Linux support only. On Windows, General, Research, and Work profiles run normally, but the Code profile needs a configured remote/container sandbox for actual shell execution. `TRUEFORGE_CODE_SANDBOX_ENABLED` therefore defaults to false on Windows, and EDITH keeps code execution on its existing local path. Set it to true only after configuring a TrueForge sandbox provider, then rerun bootstrap.

## First-time setup

1. Start EDITH on port 8000.
2. Start the pinned harness in a second terminal:

   ```powershell
   .\scripts\start_trueforge.ps1
   ```

3. Register/update the Groq-compatible provider, connector, and profiles. Bootstrap reuses `GROQ_API_KEY` locally and stores the provider credential in TrueForge's local SQLite database; it does not put the key in prompts or return it in API responses:

   ```powershell
   .\.venv\Scripts\python.exe .\scripts\bootstrap_trueforge.py
   ```

4. Check `http://127.0.0.1:8000/trueforge/status?refresh=true`. You can also open `http://localhost:8790` to inspect the saved provider and agent profiles.

Bootstrap is idempotent: it creates missing profiles and replaces manifests for existing profiles without deleting sessions.

## Configuration

```text
TRUEFORGE_ENABLED=true
TRUEFORGE_BASE_URL=http://localhost:8790
TRUEFORGE_TOKEN=
TRUEFORGE_TIMEOUT_SECONDS=600
TRUEFORGE_MODEL=groq/qwen3-6-27b
TRUEFORGE_MCP_NAME=edith-core
TRUEFORGE_MCP_URL=http://127.0.0.1:8000/mcp/
TRUEFORGE_AGENT_GENERAL=edith-general
TRUEFORGE_AGENT_RESEARCH=edith-research
TRUEFORGE_AGENT_CODE=edith-code
TRUEFORGE_AGENT_WORK=edith-work
TRUEFORGE_FALLBACK_ENABLED=true
TRUEFORGE_AUTO_BOOTSTRAP=false
TRUEFORGE_CODE_SANDBOX_ENABLED=false
```

When TrueForge OIDC is enabled, set `TRUEFORGE_TOKEN` to an ID token. Do not place provider keys in agent instructions or MCP arguments.

## Events and pauses

The bridge maps TrueForge SSE events into EDITH's existing stream:

- root `model.message.delta` → `chunk`
- tool/thread lifecycle → Activity entries
- `tool.approval_required` → Allow once / Deny card
- `tool.response_required` → inline question/options with a typed response
- `mcp.auth_required` → connector link plus an explicit continue-after-sign-in control
- structured tool artifacts → EDITH's existing artifact download cards
- `turn.done` → terminal harness status

The UI Stop button aborts the browser request and asks TrueForge to cancel the active turn. Approval decisions and question responses resume the same persisted harness session with `user.tool_approval` or `user.tool_response`; confirmation IDs are never interpreted as filenames. The app persists the last event sequence in `data/trueforge/session_map.json` and exposes a reconnect endpoint that subscribes to the active turn after that checkpoint.

Continuation endpoints used by the UI:

- `POST /trueforge/sessions/{app_session_id}/approval`
- `POST /trueforge/sessions/{app_session_id}/response`
- `POST /trueforge/sessions/{app_session_id}/resume-auth`
- `POST /trueforge/sessions/{app_session_id}/resume`
- `POST /trueforge/sessions/{app_session_id}/cancel`

## MCP boundary

`app/mcp/server.py` is deliberately thin. It delegates to the existing plugin registry and memory store instead of duplicating business logic. Read-only tools are separated from approval-gated write/browser adapters. Existing path validation, OAuth, artifact, and plugin checks remain authoritative.

## Windows sandbox limitation

TrueForge 0.1.4's local code sandbox supports macOS and Linux, not native Windows. EDITH therefore defaults `TRUEFORGE_CODE_SANDBOX_ENABLED=false` on Windows and visibly falls back to the existing code path for code requests. To run Code profile through a real isolated TrueForge sandbox, configure a supported remote sandbox provider or run the stack in Linux/WSL, then set `TRUEFORGE_CODE_SANDBOX_ENABLED=true`. Do not enable it on native Windows without a supported provider.

## Rollback

Set `TRUEFORGE_ENABLED=false` and restart EDITH. All existing Research, Homework, Work Mode, search, vision, OAuth, and artifact paths remain present. The harness mapping file can remain on disk for a later resume.
