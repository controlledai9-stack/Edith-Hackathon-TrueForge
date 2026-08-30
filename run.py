import subprocess
import sys
import os
import socket
from pathlib import Path
import uvicorn


def _port_is_available(port: int) -> bool:
    """Check the port before starting Uvicorn so Windows bind errors are actionable."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def _select_port() -> tuple[int, bool]:
    requested = int(os.getenv("EDITH_PORT", "8000"))
    if _port_is_available(requested):
        return requested, False

    # A second server holds stale in-memory keys and model state. Refuse to
    # silently create localhost:8001 unless the developer explicitly opts in.
    if os.getenv("EDITH_ALLOW_PORT_FALLBACK", "").strip() == "1":
        for candidate in range(requested + 1, requested + 11):
            if _port_is_available(candidate):
                return candidate, True
    raise OSError(
        f"Port {requested} is already occupied by another E.D.I.T.H. server. "
        "Stop that server before starting a new one. To intentionally run a second instance, "
        "set EDITH_ALLOW_PORT_FALLBACK=1."
    )
def _ensure_thinking_audio():
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.generate_thinking_audio"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path(__file__).parent),
        )
        if result.returncode != 0 and result.stderr:
            print(f"[startup] Thinking audio: {result.stderr.strip()}")
    except Exception as e:
        print(f"[startup] Thinking audio skipped: {e}")
def _validate_startup():
    from config import GROQ_API_KEY, CHATS_DATA_DIR, LEARNING_DATA_DIR
    if not GROQ_API_KEY or len(GROQ_API_KEY.strip()) < 10:
        print("[WARN] GROQ_API_KEY is missing or invalid. Chat will not work.")
    if not CHATS_DATA_DIR.exists() or not CHATS_DATA_DIR.is_dir():
        print("[WARN] CHATS_DATA_DIR does not exist or is not writable.")
    if not LEARNING_DATA_DIR.exists() or not LEARNING_DATA_DIR.is_dir():
        print("[WARN] LEARNING_DATA_DIR does not exist or is not writable.")
if __name__ == "__main__":
    _validate_startup()
    _ensure_thinking_audio()
    try:
        port, used_fallback = _select_port()
        if used_fallback:
            print(f"[WARN] Port 8000 is occupied. Multi-instance fallback was explicitly enabled.")
            print(f"[INFO] Starting E.D.I.T.H. at http://localhost:{port}")
            print("[WARN] Google/LinkedIn OAuth callbacks still configured for port 8000 will require the old server to be stopped.")
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=port,
            reload=False,
        )
    except OSError as e:
        print(f"[ERROR] Server failed to start: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[INFO] Server stopped by user.")
        
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        sys.exit(1)
