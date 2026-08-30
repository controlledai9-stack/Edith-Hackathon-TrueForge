# E.D.I.T.H. setup and troubleshooting

## Prerequisites

- Windows 10/11
- Python 3.12
- Node.js 22 or newer
- Git
- A Groq API key

Optional providers and OAuth connections are listed in `.env.example`.

## First-time setup

```powershell
git clone https://github.com/controlledai9-stack/Edith-Hackathon-TrueForge.git
cd Edith-Hackathon-TrueForge
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` locally and replace `GROQ_API_KEY=replace_with_your_key`. Never commit or share this file.

Install the pinned TrueForge runtime:

```powershell
cd trueforge
npm install
cd ..
```

## Start the application

Terminal 1 — TrueForge:

```powershell
cd trueforge
npm start
```

Terminal 2 — E.D.I.T.H.:

```powershell
.\.venv\Scripts\python.exe run.py
```

Terminal 3 — one-time TrueForge profile bootstrap:

```powershell
.\.venv\Scripts\python.exe .\scripts\bootstrap_trueforge.py
```

Open `http://localhost:8000`. TrueForge runs locally at `http://localhost:8790`.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Open `http://127.0.0.1:8000/trueforge/status?refresh=true` and confirm `ok` and `enabled` are `true`. In E.D.I.T.H., run a Work task and confirm the Activity panel shows a TrueForge harness session and tool lifecycle.

## Common problems

### PowerShell blocks environment activation

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

This changes policy only for the current terminal.

### Port 8000 is occupied

```powershell
Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
```

Stop the older E.D.I.T.H. terminal with `Ctrl+C`. Do not terminate an unrelated process.

### TrueForge is offline

Confirm `npm start` is still running in the `trueforge` directory and that `http://localhost:8790/api/v1/docs` loads. Then rerun the bootstrap command.

### Model unavailable or rate limited

Check the locally saved provider keys in Settings. Auto mode can fail over between configured providers. Never paste an API key into chat or commit it to source control.

### Research image scanning is unavailable

Add `GEMINI_API_KEY` to the private `.env` file and restart E.D.I.T.H. The configured vision model is shown in `.env.example`.

### Google services are not configured

Create a Google OAuth web client, enable the required Gmail, Tasks, Drive, and Calendar APIs, and use `http://localhost:8000/oauth/google/callback` as the redirect URI. Enter the client values through the local Plugin Manager or `.env`. OAuth tokens stay under ignored runtime storage.

## Security

- Keep both local services bound to localhost for development.
- Use synthetic/public data and dedicated demo accounts.
- Never commit `.env`, tokens, browser profiles, chats, uploads, research sources, databases, or generated artifacts.
- Review staged files and run a secret scanner before every push.

See `docs/TRUEFORGE.md` for the complete harness architecture and Windows sandbox limitation.
