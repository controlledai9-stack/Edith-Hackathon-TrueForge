# E.D.I.T.H. — TrueForge Agent Workspace

E.D.I.T.H. is a FastAPI-based agent workspace built during the TrueForge hackathon. It combines a Spider-Man-inspired interface with a real agent harness, approval-gated tools, persistent sessions, research workflows, and downloadable work artifacts.

- **E.D.I.T.H. Mode** for fast conversation, explanations, search, voice, and vision.
- **Work Mode** for multi-step tasks that use registered plugins and return downloadable documents, PDFs, spreadsheets, presentations, and images.
- **Research Mode** for source-grounded synthesis, uploaded documents, and persistent research context.
- **Homework Mode** for readable step-by-step solutions plus a separate cumulative method/formula record.

## TrueForge agent harness

Agentic and conversational work routes through the pinned local **TrueForge 0.1.4** harness. E.D.I.T.H. exposes its capabilities through a local MCP adapter, persists app-to-harness session mappings, streams harness/tool activity, displays approval and authentication pauses, and supports cancellation and continuation. The Activity panel visibly identifies TrueForge sessions and tool events so judges can see the harness doing real orchestration rather than acting as a hidden model wrapper.

Setup, configuration, security boundaries, and rollback instructions are in [docs/TRUEFORGE.md](docs/TRUEFORGE.md).

## Work Mode plugins

Working local plugins include Documents (`.docx`), PDFs, Spreadsheets (`.xlsx` with formatting/charts), Presentations (`.pptx`, 16:9), Files, Tavily web search, direct webpage reading, Gmail, and Google Tasks reminders. The Plugin Manager shows unavailable integrations as **Not configured** rather than pretending they work.

## Quick setup (Windows)

### 1. Clone and open the repository

```powershell
git clone https://github.com/controlledai9-stack/Edith-Hackathon-TrueForge.git
cd Edith-Hackathon-TrueForge
code .
```

Alternatively, open the cloned folder using **File → Open Folder** in Visual Studio Code.

### 2. Install the Python extension

Open the Extensions view with `Ctrl+Shift+X`, search for **Python**, and install the extension published by Microsoft.

### 3. Create the Python environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Then select `.venv\Scripts\python.exe` from **Python: Select Interpreter**.

### 4. Check `.env`

Create the private local configuration and add a valid Groq key:

```powershell
Copy-Item .env.example .env
```

```text
GROQ_API_KEY=your_key
TAVILY_API_KEY=optional_for_web_search
GEMINI_API_KEY=optional_for_research_scanning_and_Work_Mode_image_generation
GEMINI_VISION_MODEL=gemini-3.1-pro-preview
GEMINI_IMAGE_MODEL=gemini-3.1-flash-image
```

Do not post or share the contents of `.env`.

### 5. Install and start TrueForge

In the first terminal:

```powershell
cd trueforge
npm install
npm start
```

TrueForge runs at `http://localhost:8790`. Leave this terminal open.

### 6. Start E.D.I.T.H.

Open a second terminal in the repository root and run:

```powershell
.\.venv\Scripts\python.exe run.py
```

Wait until the terminal reports that Uvicorn is running. Then open:

```text
http://localhost:8000
```

In a third terminal, bootstrap the local TrueForge profiles once:

```powershell
.\.venv\Scripts\python.exe .\scripts\bootstrap_trueforge.py
```

Refresh E.D.I.T.H. and verify **Settings → TrueForge** reports online. Stop either service with `Ctrl+C` in its terminal.

### Optional: activate the environment first

Instead of including the interpreter path in every command, run:

```powershell
.\.venv\Scripts\Activate.ps1
python run.py
```

If PowerShell blocks activation, use this temporary terminal-only permission and try again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python run.py
```

### Visual Studio (full IDE)

If you meant **Visual Studio** rather than Visual Studio Code, install the **Python development** workload, select **File → Open → Folder**, open the cloned repository, choose `.venv\Scripts\python.exe` as the Python environment, and run `run.py`. VS Code is the simpler recommended option for this project.

For troubleshooting and detailed architecture, see [SETUP.md](SETUP.md) and [docs/TRUEFORGE.md](docs/TRUEFORGE.md).

Generated files are stored under `data/artifacts/` and served through a filename-sanitized download endpoint.

## Google connection (Gmail + Tasks + Drive + Calendar)

Create an OAuth 2.0 Web application in Google Cloud, enable the **Gmail API**, **Google Tasks API**, **Google Drive API**, and **Google Calendar API**, and authorize:

```text
http://localhost:8000/oauth/google/callback
```

Open the Plugin Manager, select **Configure** on any Google plugin, and enter `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI`; then select **Connect**. One Google connection powers Gmail, Tasks, Drive, Calendar, and Google Sheets. The same Configure flow is available for LinkedIn, Gemini Image, GitHub, and web search. Secrets are saved only to the local `.env` file and are never returned to the dashboard. E.D.I.T.H. never asks for or stores your Google password. OAuth tokens are stored locally in `data/connections/google_token.json`; short-lived OAuth state files are stored locally so a server reload does not invalidate an in-progress sign-in.

The Plugin Manager includes a **Plugin Marketplace** tab. Curated integrations can be installed with one click, and an external HTTPS manifest can be installed by URL. Marketplace plugins use the permission-gated browser workflow; downloaded manifests do not execute arbitrary code.

Reading email and creating drafts can run after connection. Sending email, uploading to Drive, and creating Calendar events require confirmation of the exact action. Google Tasks stores a due date; requested times are also placed in task notes because its API may discard the time portion.

## Security boundaries

- Tool loops are limited by `MAX_TOOL_STEPS`.
- Generated filenames and download paths are sanitized.
- File tools are restricted to E.D.I.T.H.'s data directory.
- Web readers reject local URLs and enforce response limits.
- Secrets are loaded from environment variables and are not sent to the model.
- Cloud sends and destructive operations require explicit authorization.

## Architecture and TrueForge usage

```text
Browser UI (FastAPI static frontend)
        |
        +-- deterministic commands and safety checks
        |
        +-- TrueForge session bridge (HTTP/SSE)
                    |
                    +-- General / Research / Code / Work profiles
                    +-- planning, model/tool loop, pauses, cancellation
                    +-- E.D.I.T.H. MCP server
                              |
                              +-- files, documents, PDF, Excel, PPT
                              +-- search, Google services, GitHub
                              +-- approval-gated browser and external writes
```

TrueForge owns the agent session, orchestration loop, tool approvals, inline questions, resumable turns, and streamed lifecycle events. FastAPI owns product UI, OAuth callbacks, local artifact delivery, deterministic safety checks, and the MCP tool implementations. This separation makes the harness activity observable and keeps private credentials outside model prompts.

## Verification

Run the complete regression suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The current local build passes 106 tests. For the demo, keep both E.D.I.T.H. and TrueForge visible and show the Activity panel progressing through `harness_session`, planning, tool approval, tool execution, and the final artifact.

## Cloud demo

`render.yaml` creates a separate Render web service and does not modify any existing Vercel or Render project. The hosted demo runs the E.D.I.T.H. web application and deterministic Work Mode artifact tools. TrueForge 0.1.4 standalone is intentionally disabled in the public cloud service because its bundled standalone server is local-only and is not hardened for shared internet access. Run the local setup above for the full judged TrueForge workflow.

## AI coding-assistant disclosure

AI coding assistants, including OpenAI Codex, were used during implementation for code generation, debugging, refactoring, testing, and documentation. The participant directed the product design, supplied requirements and test cases, ran and evaluated the application, selected technical trade-offs, and is responsible for understanding and explaining the submitted code.

## Security and demo-data policy

- Never commit `.env`, OAuth tokens, browser profiles, chat history, uploaded documents, generated artifacts, or databases.
- Use dedicated demo accounts and synthetic/public data in the video and screenshots.
- Never show API keys, passwords, personal email, private LinkedIn content, or login-protected information in the repository or demo.
- Only connect accounts, tools, and datasets the participant owns or has permission to use.

## Qodo Code Review Evidence

> Submission blocker until the placeholders below are replaced with real public links.

- Representative pull request: [Release E.D.I.T.H. TrueForge hackathon workspace](https://github.com/controlledai9-stack/Edith-Hackathon-TrueForge/pull/1) — open pending Qodo initial and follow-up reviews.
- What Qodo surfaced and the decision: **TODO — summarize one or two concrete findings, the implemented fixes, and any finding intentionally dismissed with a reason**
- Completed review and follow-up review: **TODO — link the Qodo review thread/check showing the initial findings, participant decisions, pushed fixes, and final follow-up review**

All substantive changes must be developed on a branch, opened as a GitHub pull request, reviewed by Qodo, addressed or explicitly dismissed, reviewed again against the final code, and only then merged. Direct pushes to `main` are not part of the project workflow.

## Submission links

- Public source repository: [controlledai9-stack/Edith-Hackathon-TrueForge](https://github.com/controlledai9-stack/Edith-Hackathon-TrueForge)
- Three-minute demo video: **TODO**
- Project write-up: this README and [docs/TRUEFORGE.md](docs/TRUEFORGE.md)
- Optional blog post: **TODO if entering the blog prize**

Licensed under the MIT License. See [LICENSE](LICENSE).
