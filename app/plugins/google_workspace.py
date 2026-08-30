from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from app.plugins.base import Plugin, ToolDefinition, ToolResult
from config import DATA_DIR

TOKEN_PATH = DATA_DIR / "connections" / "google_token.json"
OAUTH_STATE_DIR = DATA_DIR / "connections" / "google_oauth_states"
OAUTH_STATE_TTL_SECONDS = 15 * 60
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/calendar.events",
]


def _oauth_state_path(state: str) -> Path:
    digest = hashlib.sha256(state.encode("utf-8")).hexdigest()
    return OAUTH_STATE_DIR / f"{digest}.json"


def _cleanup_oauth_states(now: float | None = None) -> None:
    current = time.time() if now is None else now
    if not OAUTH_STATE_DIR.exists():
        return
    for path in OAUTH_STATE_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if current - float(payload.get("created_at", 0)) > OAUTH_STATE_TTL_SECONDS:
                path.unlink(missing_ok=True)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            path.unlink(missing_ok=True)


def _store_oauth_state(state: str, code_verifier: str | None = None) -> None:
    OAUTH_STATE_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_oauth_states()
    path = _oauth_state_path(state)
    temp = path.with_suffix(f".{secrets.token_hex(6)}.tmp")
    temp.write_text(json.dumps({"state": state, "code_verifier": code_verifier, "created_at": time.time()}), encoding="utf-8")
    temp.replace(path)


def _consume_oauth_payload(state: str) -> dict[str, Any] | None:
    path = _oauth_state_path(state)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    finally:
        path.unlink(missing_ok=True)
    created_at = float(payload.get("created_at", 0))
    stored_state = str(payload.get("state", ""))
    valid = (
        secrets.compare_digest(stored_state, state)
        and 0 <= time.time() - created_at <= OAUTH_STATE_TTL_SECONDS
    )
    return payload if valid else None


def _consume_oauth_state(state: str) -> bool:
    """Compatibility helper used by state-validation tests and older callers."""
    return _consume_oauth_payload(state) is not None


def google_configured() -> bool:
    return bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))


def _client_config() -> dict[str, Any]:
    return {"web": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/oauth/google/callback")],
    }}


def create_authorization_url() -> str:
    if not google_configured():
        raise RuntimeError("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET first")
    from google_auth_oauthlib.flow import Flow
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(96)[:128]
    flow = Flow.from_client_config(
        _client_config(), scopes=SCOPES, redirect_uri=_client_config()["web"]["redirect_uris"][0],
        state=state, code_verifier=code_verifier, autogenerate_code_verifier=False,
    )
    url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent", state=state)
    _store_oauth_state(state, code_verifier)
    return url


def finish_authorization(state: str, code: str) -> None:
    oauth_payload = _consume_oauth_payload(state)
    if not oauth_payload:
        raise ValueError("Invalid or expired OAuth state")
    code_verifier = str(oauth_payload.get("code_verifier") or "")
    if not code_verifier:
        raise ValueError("OAuth session is missing its PKCE verifier. Start the Google connection again.")
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(
        _client_config(), scopes=SCOPES, state=state, redirect_uri=_client_config()["web"]["redirect_uris"][0],
        code_verifier=code_verifier, autogenerate_code_verifier=False,
    )
    flow.fetch_token(code=code)
    credentials = flow.credentials
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = TOKEN_PATH.with_suffix(".tmp")
    temp.write_text(credentials.to_json(), encoding="utf-8")
    temp.replace(TOKEN_PATH)


def disconnect_google() -> None:
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()


def credentials():
    if not TOKEN_PATH.exists():
        return None
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds if creds.valid else None


def has_stored_google_authorization() -> bool:
    """Check authorization state without refreshing over the network."""
    if not TOKEN_PATH.exists():
        return False
    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        return bool(creds.valid or creds.refresh_token)
    except Exception:
        return False


def _schema(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


class GoogleConnectedPlugin(Plugin):
    requires_auth = True

    @property
    def connected(self) -> bool:
        # Plugin discovery must not refresh an expired token. A temporary
        # network problem should not remove every Google tool from the agent.
        return has_stored_google_authorization()

    def connect_url(self) -> str | None:
        return "/oauth/google/start" if google_configured() else None

    def disconnect(self) -> None:
        disconnect_google()


class GmailPlugin(GoogleConnectedPlugin):
    id, name = "gmail", "Gmail"
    description = "Search and read Gmail, create drafts, and send only with confirmation."
    permissions = ["read and search email", "create drafts", "send email with confirmation"]

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition("gmail_search", "Search connected Gmail using Gmail search syntax.", _schema({"query": {"type": "string"}, "max_results": {"type": "integer", "minimum": 1, "maximum": 20}}, ["query"]), self.search),
            ToolDefinition("gmail_read", "Read a Gmail message by message id.", _schema({"message_id": {"type": "string"}}, ["message_id"]), self.read),
            ToolDefinition("gmail_recent", "List recent Gmail messages.", _schema({"max_results": {"type": "integer", "minimum": 1, "maximum": 20}}), self.recent),
            ToolDefinition("gmail_create_draft", "Create an email draft without sending it.", _schema({"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}, ["to", "subject", "body"]), self.create_draft),
            ToolDefinition("gmail_send", "Send an email. Set confirmed=true only after the user explicitly confirms the exact send action.", _schema({"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}, "confirmed": {"type": "boolean"}}, ["to", "subject", "body", "confirmed"]), self.send, requires_confirmation=True),
        ]

    def _service(self):
        from googleapiclient.discovery import build
        creds = credentials()
        if not creds: raise RuntimeError("Gmail is not connected")
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    @staticmethod
    def _summary(message: dict) -> dict:
        headers = {item["name"].lower(): item["value"] for item in message.get("payload", {}).get("headers", [])}
        return {"id": message.get("id"), "thread_id": message.get("threadId"), "from": headers.get("from"), "to": headers.get("to"), "subject": headers.get("subject"), "date": headers.get("date"), "snippet": message.get("snippet")}

    def search(self, query: str, max_results: int = 10) -> ToolResult:
        try:
            service = self._service()
            ids = service.users().messages().list(userId="me", q=query, maxResults=min(max_results, 20)).execute().get("messages", [])
            messages = [self._summary(service.users().messages().get(userId="me", id=item["id"], format="metadata").execute()) for item in ids]
            return ToolResult(True, self.id, "gmail_search", data={"messages": messages}, message=f"Found {len(messages)} emails")
        except Exception as exc: return ToolResult(False, self.id, "gmail_search", error=str(exc), message="Gmail search failed")

    def recent(self, max_results: int = 10) -> ToolResult:
        return self.search("in:anywhere", max_results)

    def read(self, message_id: str) -> ToolResult:
        try:
            message = self._service().users().messages().get(userId="me", id=message_id, format="full").execute()
            parts = message.get("payload", {}).get("parts") or [message.get("payload", {})]
            body = ""
            for part in parts:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body += base64.urlsafe_b64decode(part["body"]["data"] + "===").decode("utf-8", errors="replace")
            return ToolResult(True, self.id, "gmail_read", data={**self._summary(message), "body": body[:100_000]}, message="Email read")
        except Exception as exc: return ToolResult(False, self.id, "gmail_read", error=str(exc), message="Email reading failed")

    @staticmethod
    def _raw(to: str, subject: str, body: str) -> dict:
        message = EmailMessage(); message["To"] = to; message["Subject"] = subject; message.set_content(body)
        return {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}

    def create_draft(self, to: str, subject: str, body: str) -> ToolResult:
        try:
            draft = self._service().users().drafts().create(userId="me", body={"message": self._raw(to, subject, body)}).execute()
            return ToolResult(True, self.id, "gmail_create_draft", data={"draft_id": draft.get("id")}, message="Gmail draft created")
        except Exception as exc: return ToolResult(False, self.id, "gmail_create_draft", error=str(exc), message="Draft creation failed")

    def send(self, to: str, subject: str, body: str, confirmed: bool = False) -> ToolResult:
        if not confirmed:
            return ToolResult(False, self.id, "gmail_send", data={"to": to, "subject": subject, "body": body}, message=f"Please confirm sending this email to {to} with subject '{subject}'.", confirmation_required=True)
        try:
            sent = self._service().users().messages().send(userId="me", body=self._raw(to, subject, body)).execute()
            return ToolResult(True, self.id, "gmail_send", data={"message_id": sent.get("id")}, message="Email sent")
        except Exception as exc: return ToolResult(False, self.id, "gmail_send", error=str(exc), message="Email sending failed")


class GoogleTasksPlugin(GoogleConnectedPlugin):
    id, name = "google_tasks", "Google Tasks"
    description = "Create, list, and complete reminders using Google Tasks."
    permissions = ["read tasks", "create reminders", "complete tasks"]

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition("google_tasks_list", "List incomplete Google Tasks.", _schema({"max_results": {"type": "integer", "minimum": 1, "maximum": 100}}), self.list_tasks),
            ToolDefinition("google_tasks_create", "Create a task/reminder. due must be RFC3339. Google Tasks stores the due date; include any requested time in notes.", _schema({"title": {"type": "string"}, "notes": {"type": "string"}, "due": {"type": "string"}}, ["title"]), self.create_task),
            ToolDefinition("google_tasks_complete", "Mark a Google Task complete by id.", _schema({"task_id": {"type": "string"}}, ["task_id"]), self.complete_task),
        ]

    def _service(self):
        from googleapiclient.discovery import build
        creds = credentials()
        if not creds: raise RuntimeError("Google Tasks is not connected")
        return build("tasks", "v1", credentials=creds, cache_discovery=False)

    def list_tasks(self, max_results: int = 20) -> ToolResult:
        try:
            items = self._service().tasks().list(tasklist="@default", showCompleted=False, maxResults=min(max_results, 100)).execute().get("items", [])
            return ToolResult(True, self.id, "google_tasks_list", data={"tasks": items}, message=f"Found {len(items)} tasks")
        except Exception as exc: return ToolResult(False, self.id, "google_tasks_list", error=str(exc), message="Could not list Google Tasks")

    def create_task(self, title: str, notes: str = "", due: str | None = None) -> ToolResult:
        try:
            body = {"title": title, "notes": notes}
            if due:
                parsed = datetime.fromisoformat(due.replace("Z", "+00:00"))
                body["due"] = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            task = self._service().tasks().insert(tasklist="@default", body=body).execute()
            return ToolResult(True, self.id, "google_tasks_create", data={"task": task}, message=f"Google Task created: {title}")
        except Exception as exc: return ToolResult(False, self.id, "google_tasks_create", error=str(exc), message="Could not create Google Task")

    def complete_task(self, task_id: str) -> ToolResult:
        try:
            service = self._service(); task = service.tasks().get(tasklist="@default", task=task_id).execute(); task["status"] = "completed"
            updated = service.tasks().update(tasklist="@default", task=task_id, body=task).execute()
            return ToolResult(True, self.id, "google_tasks_complete", data={"task": updated}, message="Google Task marked complete")
        except Exception as exc: return ToolResult(False, self.id, "google_tasks_complete", error=str(exc), message="Could not complete Google Task")


class GoogleDrivePlugin(GoogleConnectedPlugin):
    id, name = "google_drive", "Google Drive"
    description = "Find E.D.I.T.H.-created Drive files and upload generated artifacts with confirmation."
    permissions = ["view files created by E.D.I.T.H.", "upload generated files with confirmation"]

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition("google_drive_list", "List files in Google Drive that E.D.I.T.H. is allowed to access.", _schema({"query": {"type": "string"}, "max_results": {"type": "integer", "minimum": 1, "maximum": 100}}), self.list_files),
            ToolDefinition("google_drive_upload", "Upload a generated artifact to Google Drive. confirmed may be true only after the user authorizes this exact upload.", _schema({"path": {"type": "string"}, "name": {"type": "string"}, "confirmed": {"type": "boolean"}}, ["path", "confirmed"]), self.upload, requires_confirmation=True),
        ]

    def _service(self):
        from googleapiclient.discovery import build
        creds = credentials()
        if not creds: raise RuntimeError("Google Drive is not connected")
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    def list_files(self, query: str = "", max_results: int = 20) -> ToolResult:
        try:
            escaped = str(query).replace("'", "\\'").strip()
            drive_query = "trashed = false"
            if escaped:
                drive_query += f" and name contains '{escaped}'"
            files = self._service().files().list(
                q=drive_query,
                pageSize=min(max_results, 100),
                fields="files(id,name,mimeType,modifiedTime,webViewLink,size)",
                orderBy="modifiedTime desc",
            ).execute().get("files", [])
            return ToolResult(True, self.id, "google_drive_list", data={"files": files}, message=f"Found {len(files)} Drive files")
        except Exception as exc:
            return ToolResult(False, self.id, "google_drive_list", error=str(exc), message="Could not list Google Drive files")

    def upload(self, path: str, confirmed: bool = False, name: str = "") -> ToolResult:
        if not confirmed:
            return ToolResult(False, self.id, "google_drive_upload", data={"path": path, "name": name}, message=f"Please confirm uploading {name or Path(path).name} to Google Drive.", confirmation_required=True)
        try:
            import mimetypes
            from googleapiclient.http import MediaFileUpload
            from app.plugins.utils import approved_path
            source = approved_path(path)
            mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            media = MediaFileUpload(str(source), mimetype=mime_type, resumable=False)
            uploaded = self._service().files().create(
                body={"name": name or source.name}, media_body=media, fields="id,name,mimeType,webViewLink"
            ).execute()
            return ToolResult(True, self.id, "google_drive_upload", data={"file": uploaded}, message=f"Uploaded {uploaded.get('name')} to Google Drive")
        except Exception as exc:
            return ToolResult(False, self.id, "google_drive_upload", error=str(exc), message="Google Drive upload failed")


class GoogleCalendarPlugin(GoogleConnectedPlugin):
    id, name = "google_calendar", "Google Calendar"
    description = "Review upcoming events and create calendar events with confirmation."
    permissions = ["read calendar events", "create events with confirmation"]

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition("google_calendar_list", "List upcoming Google Calendar events. Times must be RFC3339 when supplied.", _schema({"time_min": {"type": "string"}, "time_max": {"type": "string"}, "max_results": {"type": "integer", "minimum": 1, "maximum": 100}}), self.list_events),
            ToolDefinition("google_calendar_create", "Create a Google Calendar event. start and end must be RFC3339. confirmed may be true only when the current user message authorizes this exact event.", _schema({"summary": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}, "description": {"type": "string"}, "location": {"type": "string"}, "time_zone": {"type": "string"}, "confirmed": {"type": "boolean"}}, ["summary", "start", "end", "confirmed"]), self.create_event, requires_confirmation=True),
        ]

    def _service(self):
        from googleapiclient.discovery import build
        creds = credentials()
        if not creds: raise RuntimeError("Google Calendar is not connected")
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    def list_events(self, time_min: str = "", time_max: str = "", max_results: int = 20) -> ToolResult:
        try:
            minimum = time_min or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            kwargs = {"calendarId": "primary", "timeMin": minimum, "maxResults": min(max_results, 100), "singleEvents": True, "orderBy": "startTime"}
            if time_max: kwargs["timeMax"] = time_max
            events = self._service().events().list(**kwargs).execute().get("items", [])
            return ToolResult(True, self.id, "google_calendar_list", data={"events": events}, message=f"Found {len(events)} calendar events")
        except Exception as exc:
            return ToolResult(False, self.id, "google_calendar_list", error=str(exc), message="Could not list calendar events")

    def create_event(self, summary: str, start: str, end: str, confirmed: bool = False, description: str = "", location: str = "", time_zone: str = "") -> ToolResult:
        details = {"summary": summary, "start": start, "end": end, "description": description, "location": location, "time_zone": time_zone}
        if not confirmed:
            return ToolResult(False, self.id, "google_calendar_create", data=details, message=f"Please confirm creating '{summary}' from {start} to {end}.", confirmation_required=True)
        try:
            start_body, end_body = {"dateTime": start}, {"dateTime": end}
            if time_zone:
                start_body["timeZone"] = time_zone; end_body["timeZone"] = time_zone
            body = {"summary": summary, "start": start_body, "end": end_body}
            if description: body["description"] = description
            if location: body["location"] = location
            event = self._service().events().insert(calendarId="primary", body=body).execute()
            return ToolResult(True, self.id, "google_calendar_create", data={"event": event}, message=f"Created calendar event: {summary}")
        except Exception as exc:
            return ToolResult(False, self.id, "google_calendar_create", error=str(exc), message="Could not create calendar event")
