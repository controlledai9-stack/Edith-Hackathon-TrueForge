from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

from app.plugins.base import Plugin, ToolDefinition, ToolResult
from app.plugins.utils import approved_path
from config import DATA_DIR


TOKEN_PATH = DATA_DIR / "connections" / "linkedin_token.json"
STATE_DIR = DATA_DIR / "connections" / "linkedin_oauth_states"
PENDING_PATH = DATA_DIR / "work_mode" / "pending_linkedin_posts.json"
STATE_TTL_SECONDS = 15 * 60


def _state_path(state: str) -> Path:
    return STATE_DIR / f"{hashlib.sha256(state.encode('utf-8')).hexdigest()}.json"


def linkedin_configured() -> bool:
    return bool(os.getenv("LINKEDIN_CLIENT_ID") and os.getenv("LINKEDIN_CLIENT_SECRET"))


def create_linkedin_authorization_url() -> str:
    if not linkedin_configured():
        raise RuntimeError("Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in .env first")
    state = secrets.token_urlsafe(32)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _state_path(state).write_text(json.dumps({"state": state, "created_at": time.time()}), encoding="utf-8")
    query = urlencode({
        "response_type": "code",
        "client_id": os.getenv("LINKEDIN_CLIENT_ID", ""),
        "redirect_uri": os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:8000/oauth/linkedin/callback"),
        "state": state,
        "scope": "openid profile w_member_social",
    })
    return f"https://www.linkedin.com/oauth/v2/authorization?{query}"


def finish_linkedin_authorization(state: str, code: str) -> None:
    path = _state_path(state)
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid or expired LinkedIn OAuth state") from exc
    finally:
        path.unlink(missing_ok=True)
    if not secrets.compare_digest(str(stored.get("state", "")), state) or time.time() - float(stored.get("created_at", 0)) > STATE_TTL_SECONDS:
        raise ValueError("Invalid or expired LinkedIn OAuth state")
    response = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": os.getenv("LINKEDIN_CLIENT_ID", ""),
        "client_secret": os.getenv("LINKEDIN_CLIENT_SECRET", ""),
        "redirect_uri": os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:8000/oauth/linkedin/callback"),
    }, timeout=30)
    response.raise_for_status()
    token = response.json()
    access_token = token["access_token"]
    profile = requests.get("https://api.linkedin.com/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
    profile.raise_for_status()
    subject = str(profile.json().get("sub") or "").strip()
    if not subject:
        raise RuntimeError("LinkedIn did not return the authenticated member ID")
    token["author"] = f"urn:li:person:{subject}"
    token["expires_at"] = time.time() + int(token.get("expires_in", 0))
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = TOKEN_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(token, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(TOKEN_PATH)


def _token() -> dict | None:
    try:
        token = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
        if float(token.get("expires_at", 0)) <= time.time() + 30:
            return None
        return token
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _schema(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


class LinkedInPlugin(Plugin):
    id, name = "linkedin", "LinkedIn"
    description = "Publish confirmed text-and-image posts through LinkedIn's official API."
    permissions = ["identify the connected LinkedIn member", "upload post images", "publish only after confirmation"]
    requires_auth = True

    @property
    def connected(self) -> bool:
        return _token() is not None

    def connect_url(self) -> str | None:
        return "/oauth/linkedin/start" if linkedin_configured() else None

    def disconnect(self) -> None:
        TOKEN_PATH.unlink(missing_ok=True)

    def get_tools(self) -> list[ToolDefinition]:
        return [ToolDefinition(
            "linkedin_publish",
            "Publish one image and caption to the connected member's LinkedIn feed. Always stage with confirmed=false first.",
            _schema({
                "caption": {"type": "string"},
                "image_path": {"type": "string"},
                "confirmed": {"type": "boolean"},
                "confirmation_id": {"type": "string"},
            }, ["caption", "image_path", "confirmed"]),
            self.publish,
            requires_confirmation=True,
        )]

    @staticmethod
    def _load_pending() -> dict:
        try:
            value = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _save_pending(value: dict) -> None:
        PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = PENDING_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(PENDING_PATH)

    def cancel_pending(self, confirmation_id: str) -> None:
        pending = self._load_pending()
        if pending.pop(str(confirmation_id), None) is not None:
            self._save_pending(pending)

    def publish(self, caption: str, image_path: str, confirmed: bool = False, confirmation_id: str = "") -> ToolResult:
        if not self.connected:
            return ToolResult(False, self.id, "linkedin_publish", error="LinkedIn is not connected", message="Connect LinkedIn in the Work Mode Plugin Manager before publishing.")
        try:
            image = approved_path(image_path)
            if not confirmed:
                confirmation_id = secrets.token_hex(4)
                pending = self._load_pending()
                pending[confirmation_id] = {"caption": str(caption), "image_path": str(image)}
                self._save_pending(pending)
                return ToolResult(
                    False,
                    self.id,
                    "linkedin_publish",
                    data={"confirmation_id": confirmation_id, "pending_linkedin_post": {"caption": str(caption), "image_path": str(image)}},
                    message=f"Please confirm this LinkedIn post [{confirmation_id}] using {image.name}.\n\nPrepared content:\n{caption}",
                    confirmation_required=True,
                )
            pending = self._load_pending()
            exact = pending.get(str(confirmation_id))
            if not exact:
                raise ValueError("Pending LinkedIn post was not found or has expired")
            image = approved_path(exact["image_path"])
            caption = exact["caption"]
            token = _token()
            if not token:
                raise RuntimeError("LinkedIn connection expired; reconnect it in the Plugin Manager")
            headers = {
                "Authorization": f"Bearer {token['access_token']}",
                "Linkedin-Version": os.getenv("LINKEDIN_API_VERSION", "202607"),
                "X-Restli-Protocol-Version": "2.0.0",
                "Content-Type": "application/json",
            }
            initialized = requests.post(
                "https://api.linkedin.com/rest/images?action=initializeUpload",
                headers=headers,
                json={"initializeUploadRequest": {"owner": token["author"]}},
                timeout=30,
            )
            initialized.raise_for_status()
            value = initialized.json()["value"]
            upload = requests.put(value["uploadUrl"], headers={"Authorization": headers["Authorization"]}, data=image.read_bytes(), timeout=120)
            upload.raise_for_status()
            posted = requests.post("https://api.linkedin.com/rest/posts", headers=headers, json={
                "author": token["author"],
                "commentary": caption,
                "visibility": "PUBLIC",
                "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
                "content": {"media": {"id": value["image"], "altText": "E.D.I.T.H. Work Mode announcement"}},
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            }, timeout=30)
            posted.raise_for_status()
            post_id = posted.headers.get("x-restli-id", "")
            pending.pop(str(confirmation_id), None)
            self._save_pending(pending)
            return ToolResult(True, self.id, "linkedin_publish", data={"post_id": post_id}, message="LinkedIn post published successfully.")
        except Exception as exc:
            return ToolResult(False, self.id, "linkedin_publish", error=str(exc), message="LinkedIn publishing failed")
