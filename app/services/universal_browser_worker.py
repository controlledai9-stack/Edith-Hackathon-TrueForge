from __future__ import annotations

import json
import os
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from config import DATA_DIR, GROQ_API_KEYS, GROQ_MODEL


JOBS_DIR = DATA_DIR / "browser_jobs"
PROFILE_DIR = DATA_DIR / "browser_profile"
MAX_STEPS = max(4, min(int(os.getenv("UNIVERSAL_BROWSER_MAX_STEPS", "24")), 50))
AUTH_WAIT_SECONDS = max(60, min(int(os.getenv("UNIVERSAL_BROWSER_AUTH_WAIT_SECONDS", "600")), 1800))
LOCK_PATH = DATA_DIR / "browser_worker.lock"
HEADLESS = os.getenv("UNIVERSAL_BROWSER_HEADLESS", "false").strip().lower() not in {"0", "false", "no", "off"}


def _path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _read(job_id: str) -> dict[str, Any]:
    return json.loads(_path(job_id).read_text(encoding="utf-8"))


def _update(job_id: str, **changes: Any) -> dict[str, Any]:
    payload = _read(job_id)
    payload.update(changes)
    payload["updated_at"] = time.time()
    temporary = _path(job_id).with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(_path(job_id))
    return payload


def _cancelled(job_id: str) -> bool:
    return _read(job_id).get("status") == "cancelled"


def _capture(job_id: str, page: Any) -> None:
    """Keep the legacy screenshot available only for explicitly headless runs."""
    if not HEADLESS:
        return
    try:
        page.screenshot(path=str(_path(job_id).with_suffix(".jpg")), type="jpeg", quality=72, full_page=False, timeout=12_000)
        _update(job_id, preview_updated_at=time.time())
    except Exception:
        pass


def _native_window_geometry() -> tuple[int, int, int, int]:
    """Place the shared browser beside E.D.I.T.H. without covering the full screen."""
    screen_width, screen_height = 1440, 900
    if os.name == "nt":
        try:
            import ctypes

            screen_width = int(ctypes.windll.user32.GetSystemMetrics(0))
            screen_height = int(ctypes.windll.user32.GetSystemMetrics(1))
        except Exception:
            pass
    width = max(560, min(900, int(screen_width * 0.45)))
    height = max(640, screen_height - 80)
    left = max(0, screen_width - width)
    return left, 0, width, height


@contextmanager
def _exclusive_browser(job_id: str):
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK_PATH.open("a+b")
    acquired = False
    try:
        while not acquired:
            if _cancelled(job_id):
                yield False
                return
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    if handle.tell() == handle.seek(0, 2) and handle.tell() == 0:
                        handle.write(b"0"); handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except (OSError, BlockingIOError):
                _update(job_id, status="queued", message="Waiting for the active browser workflow to finish")
                time.sleep(1)
        yield True
    finally:
        if acquired:
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


def _browser_executable() -> str | None:
    configured = os.getenv("UNIVERSAL_BROWSER_EXECUTABLE", "").strip()
    candidates = [
        configured,
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    return next((value for value in candidates if value and Path(value).is_file()), None)


def _auth_visible(page: Any) -> bool:
    try:
        if page.locator('input[type="password"]:visible, input[autocomplete="one-time-code"]:visible, iframe[src*="captcha"]:visible, iframe[title*="captcha" i]:visible').count() > 0:
            return True
        text = page.locator("body").inner_text(timeout=2500).lower()[:6000]
        url = page.url.lower()
        if re.search(r"\b(?:verify you are human|security challenge|enter (?:the )?(?:verification|security) code|complete the captcha)\b", text):
            return True
        return bool(
            re.search(r"/(?:login|signin|auth)(?:/|\?|$)", url)
            and re.search(r"\b(?:log in|sign in|password|verification code|two.factor|captcha)\b", text)
        )
    except Exception:
        return False


def _latest_open_page(page: Any) -> Any:
    pages = [candidate for candidate in page.context.pages if not candidate.is_closed()]
    return pages[-1] if pages else page


def _apply_interactive_command(job_id: str, page: Any, command: dict[str, Any]) -> Any:
    """Apply a local preview interaction without adding sensitive text to browser history."""
    active_page = _latest_open_page(page)
    kind = str(command.get("type") or "").lower()
    # Clear the on-disk command before executing it, especially typed secrets.
    _update(job_id, interactive_command=None, interactive_ack=command.get("id"), message="Browser interaction applied")
    if kind == "click":
        active_page.mouse.click(float(command.get("x", 0)), float(command.get("y", 0)))
    elif kind == "type":
        active_page.keyboard.insert_text(str(command.get("text") or ""))
    elif kind == "key":
        active_page.keyboard.press(str(command.get("key") or "Enter"))
    elif kind == "scroll":
        active_page.mouse.wheel(0, int(command.get("delta_y", 0)))
    active_page.wait_for_timeout(350)
    active_page = _latest_open_page(active_page)
    _capture(job_id, active_page)
    _update(job_id, status="waiting_for_auth", message="Interactive sign-in is ready", current_url=active_page.url)
    return active_page


def _wait_for_private_auth(job_id: str, page: Any) -> Any | None:
    _capture(job_id, page)
    if HEADLESS:
        _update(
            job_id, status="waiting_for_auth",
            message="Sign in inside the interactive preview. Click the page, use the private typing box, and E.D.I.T.H. will continue automatically.",
            current_url=page.url,
        )
        deadline = time.time() + AUTH_WAIT_SECONDS
        while time.time() < deadline:
            payload = _read(job_id)
            if payload.get("status") == "cancelled":
                return None
            command = payload.get("interactive_command")
            if isinstance(command, dict):
                try:
                    page = _apply_interactive_command(job_id, page, command)
                except Exception as exc:
                    _update(
                        job_id, interactive_command=None, interactive_ack=command.get("id"),
                        status="waiting_for_auth", message="That interaction could not be applied; try again",
                        transient_error=str(exc)[:500], current_url=getattr(page, "url", ""),
                    )
            else:
                page = _latest_open_page(page)
                if not _auth_visible(page):
                    _update(job_id, status="running", message="Authentication completed; resuming browser workflow", current_url=page.url)
                    return page
                time.sleep(0.2)
        _update(job_id, status="waiting_for_user", message="Interactive sign-in timed out. Retry the Work Mode task to open a fresh session.")
        return None
    _update(job_id, status="waiting_for_auth", message="Sign in privately in the opened browser. E.D.I.T.H. will continue automatically after authentication.", current_url=page.url)
    deadline = time.time() + AUTH_WAIT_SECONDS
    while time.time() < deadline:
        if _cancelled(job_id):
            return None
        if not _auth_visible(page):
            _update(job_id, status="running", message="Authentication completed; resuming browser workflow", current_url=page.url)
            return page
        time.sleep(0.4)
    _update(job_id, status="waiting_for_user", message="Authentication timed out. Retry the Work Mode task after signing in to the persistent browser profile.")
    return None


def _page_state(page: Any, annotate: bool = True) -> dict[str, Any]:
    elements = page.evaluate("""
    (annotate) => {
      const selectors = 'a[href],button,input,textarea,select,[contenteditable="true"],[role="button"],[role="textbox"]';
      const dialogs = Array.from(document.querySelectorAll('[role="dialog"]')).filter(dialog => {
        const r = dialog.getBoundingClientRect(); const s = getComputedStyle(dialog);
        return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none';
      });
      const prioritized = [...dialogs.flatMap(dialog => Array.from(dialog.querySelectorAll(selectors))), ...Array.from(document.querySelectorAll(selectors))];
      return Array.from(new Set(prioritized)).filter(el => {
        const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
        return (el.tagName === 'INPUT' && el.type === 'file') ||
          (r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none');
      }).slice(0, 140).map((el, index) => {
        const id = `e${index}`;
        if (annotate) el.setAttribute('data-edith-id', id);
        const label = el.labels?.[0]?.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '';
        return {id, tag: el.tagName.toLowerCase(), type: el.type || '', text: (el.innerText || el.value || '').trim().slice(0,240), label: label.trim().slice(0,180), placeholder: (el.placeholder || '').slice(0,180), href: (el.href || '').slice(0,500), disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true'};
      });
    }
    """, annotate)
    try:
        body = page.locator("body").inner_text(timeout=4000)[:14_000]
    except Exception:
        body = ""
    return {"url": page.url, "title": page.title(), "body": body, "elements": elements}


def _next_action(task: dict[str, Any], state: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": (
            "You control a browser to complete one confirmed user task. Return JSON only with one action. "
            "Allowed actions: click {id}, fill {id,value}, upload {id,file_index}, select {id,value}, press {id,key}, wait, done {evidence}, or user {message}. "
            "Use only element IDs in the supplied state. After clicking something that opens a composer, dialog, menu, or new page, choose click and let the next browser step inspect the new elements. "
            "Never ask the user to provide element IDs, selectors, page HTML, or UI details. Discover those by clicking and re-inspecting the page. "
            "Return user only for private authentication, CAPTCHA, security checks, or genuinely missing task content. "
            "Never fill password, OTP, payment, CAPTCHA, or security-answer fields; return user for those. "
            "The final publish/post/submit action is authorized because the application already obtained exact user confirmation. "
            "Do not claim success until the page visibly confirms it or the resulting URL/content is strong evidence."
        )},
        {"role": "user", "content": json.dumps({"task": task, "page": state, "recent_actions": history[-8:]}, ensure_ascii=False)},
    ]
    last_error: Exception | None = None
    for attempt in range(max(3, len(GROQ_API_KEYS) * 2)):
        try:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEYS[attempt % len(GROQ_API_KEYS)])
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                temperature=0.05,
                response_format={"type": "json_object"},
            )
            value = json.loads(response.choices[0].message.content or "{}")
            return value if isinstance(value, dict) else {"action": "wait"}
        except Exception as exc:
            last_error = exc
            message = str(exc).lower()
            if not any(token in message for token in ("429", "rate limit", "rate_limit", "temporarily", "timeout")):
                raise
            time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"Browser planner rate limit did not clear: {last_error}")


def _element_text(element: dict[str, Any]) -> str:
    return " ".join(str(element.get(key, "")) for key in ("text", "label", "placeholder")).strip().lower()


def _linkedin_action(task: dict[str, Any], state: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Handle LinkedIn's multi-dialog post composer without exposing DOM IDs to the user."""
    if "linkedin.com" not in state.get("url", "").lower() or task.get("action_type") not in {"publish", "post", "upload"}:
        return None
    elements = state.get("elements", [])
    context = str(task.get("context") or "").strip()
    files = task.get("files") or []
    body = state.get("body", "")
    uploaded = any(action.get("_intent") == "linkedin_upload" and action.get("_executed") for action in history)
    publish_clicked = any(action.get("_intent") == "linkedin_publish" and action.get("_executed") for action in history)

    editor = next((element for element in elements if element.get("tag") == "textarea" or
                   (element.get("tag") in {"div", "p"} and "textbox" in _element_text(element)) or
                   (element.get("tag") not in {"button", "a", "input"} and "editor" in _element_text(element))), None)
    composer_open = editor is not None or "create a post" in body.lower()

    if publish_clicked and not composer_open and (not context or context[:45] in body):
        return {"action": "done", "evidence": "LinkedIn closed the post composer and the approved post content is visible in the feed."}

    if not composer_open:
        start = next((element for element in elements if "start a post" in _element_text(element)), None)
        if start:
            return {"action": "click", "id": start["id"], "_intent": "linkedin_open_composer"}

    if editor and context and context[:45] not in body:
        return {"action": "fill", "id": editor["id"], "value": context, "_intent": "linkedin_fill_caption"}

    if files and not uploaded:
        file_input = next((element for element in elements if element.get("type") == "file"), None)
        if file_input:
            return {"action": "upload", "id": file_input["id"], "file_index": 0, "_intent": "linkedin_upload"}
        media = next((element for element in elements if any(label in _element_text(element) for label in ("add media", "photo", "media")) and element.get("tag") in {"button", "div"}), None)
        if media:
            return {"action": "click", "id": media["id"], "_intent": "linkedin_open_media"}

    if uploaded:
        next_button = next((element for element in elements if not element.get("disabled") and _element_text(element) in {"next", "done"}), None)
        if next_button:
            return {"action": "click", "id": next_button["id"], "_intent": "linkedin_media_next"}

    if composer_open and context and (not files or uploaded):
        post_button = next((element for element in reversed(elements) if not element.get("disabled") and
                            element.get("tag") in {"button", "div"} and _element_text(element) in {"post", "publish"}), None)
        if post_button:
            return {"action": "click", "id": post_button["id"], "_intent": "linkedin_publish"}
    return None


def _locator(page: Any, element_id: str) -> Any:
    if not re.fullmatch(r"e\d+", str(element_id or "")):
        raise ValueError("Invalid browser element ID")
    return page.locator(f'[data-edith-id="{element_id}"]').first


def _execute_linkedin_action(page: Any, task: dict[str, Any], action: dict[str, Any]) -> bool:
    """Use stable LinkedIn semantics when its React tree replaces annotated nodes mid-action."""
    intent = action.get("_intent")
    if not intent:
        return False
    if intent == "linkedin_open_composer":
        overlay = page.locator("#interop-outlet").first
        if overlay.count() > 0:
            overlay.evaluate("(el) => el.style.setProperty('pointer-events', 'none', 'important')")
        target = page.locator('[data-view-name="share-sharebox-focus"] [aria-label="Start a post"]').first
        if target.count() == 0:
            target = page.get_by_text("Start a post", exact=True).first
        target.click(timeout=15_000)
    elif intent == "linkedin_fill_caption":
        editor = page.get_by_label("Text editor for creating content", exact=True).last
        editor.fill(str(task.get("context") or ""), timeout=15_000)
    elif intent == "linkedin_open_media":
        target = page.get_by_role("button", name="Add media", exact=True).last
        target.click(timeout=15_000)
    elif intent == "linkedin_upload":
        files = task.get("files") or []
        if not files:
            raise ValueError("Requested LinkedIn attachment is unavailable")
        page.locator('input[type="file"]').last.set_input_files([item["path"] for item in files[:5]], timeout=60_000)
    elif intent == "linkedin_media_next":
        page.get_by_role("button", name=re.compile(r"^(?:next|done)$", re.I)).last.click(timeout=15_000)
    elif intent == "linkedin_publish":
        page.get_by_role("button", name=re.compile(r"^(?:post|publish)$", re.I)).last.click(timeout=15_000)
    else:
        return False
    return True


def _wait_until_enabled(locator: Any, timeout_ms: int = 30_000) -> None:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if locator.count() > 0 and locator.is_visible() and locator.is_enabled():
            return
        time.sleep(0.25)
    raise TimeoutError("LinkedIn control did not become enabled")


def _unblock_click_target(locator: Any) -> None:
    """Disable only foreign DOM layers that physically cover a confirmed control."""
    locator.evaluate("""
    (target) => {
      const rect = target.getBoundingClientRect();
      const x = rect.left + rect.width / 2;
      const y = rect.top + rect.height / 2;
      for (let attempt = 0; attempt < 24; attempt += 1) {
        const blocker = document.elementFromPoint(x, y);
        if (!blocker || blocker === target || target.contains(blocker) || blocker.contains(target)) return;
        blocker.style.setProperty('pointer-events', 'none', 'important');
      }
    }
    """)


def _ensure_linkedin_caption(page: Any, caption: str) -> None:
    """Make caption state independent of LinkedIn's zero/single/multi-media dialogs."""
    if not str(caption).strip():
        return
    expected = " ".join(str(caption).split())[:80]
    editor = page.get_by_label("Text editor for creating content", exact=True).last
    editor.wait_for(state="visible", timeout=20_000)
    current = " ".join((editor.inner_text(timeout=8_000) or "").split())
    if expected and expected in current:
        return
    editor.evaluate("(el) => el.focus()")
    page.keyboard.press("Control+A")
    page.keyboard.insert_text(caption)
    page.keyboard.press("End")
    page.keyboard.press(" ")
    page.keyboard.press("Backspace")
    current = " ".join((editor.inner_text(timeout=8_000) or "").split())
    if expected and expected not in current:
        raise ValueError("LinkedIn did not retain the approved caption in the composer")


def _run_linkedin_publish(job_id: str, page: Any, task: dict[str, Any]) -> bool:
    """Complete LinkedIn's known post flow as one transaction, outside the generic planner."""
    if "linkedin.com" not in page.url.lower() or task.get("action_type") not in {"publish", "post", "upload"}:
        return False
    context_text = str(task.get("context") or "").strip()
    files = task.get("files") or []
    if not context_text and not files:
        raise ValueError("The approved LinkedIn post has no text or media")

    profile_activity_url = ""
    try:
        profile_links = page.locator('a[href*="linkedin.com/in/"], a[href^="/in/"]')
        for index in range(min(profile_links.count(), 12)):
            href = str(profile_links.nth(index).get_attribute("href") or "")
            match = re.search(r"(?:https://www\.linkedin\.com)?(/in/[^/?#]+)", href)
            if match:
                profile_activity_url = f"https://www.linkedin.com{match.group(1)}/recent-activity/all/"
                break
    except Exception:
        profile_activity_url = ""

    _update(job_id, status="running", message="Opening LinkedIn post composer", current_url=page.url, step=1)
    overlay = page.locator("#interop-outlet").first
    if overlay.count() > 0:
        overlay.evaluate("(el) => el.style.setProperty('pointer-events', 'none', 'important')")
    start = page.locator('[data-view-name="share-sharebox-focus"] [aria-label="Start a post"]').first
    start.wait_for(state="visible", timeout=20_000)
    _unblock_click_target(start)
    start.click(timeout=20_000)
    _capture(job_id, page)

    editor = page.get_by_label("Text editor for creating content", exact=True).last
    editor.wait_for(state="visible", timeout=20_000)
    _update(job_id, message="Adding the approved LinkedIn caption", step=2)
    # LinkedIn's rich-text editor may visually accept fill() without updating
    # its internal composer state. Real keyboard insertion enables Post/Save.
    if context_text:
        _ensure_linkedin_caption(page, context_text)
    _capture(job_id, page)

    if files:
        attachment_label = files[0].get("name") or "the approved attachment" if len(files) == 1 else f"{len(files[:5])} approved attachments"
        _update(job_id, message=f"Uploading {attachment_label}", step=3)
        media_button = page.get_by_role("button", name="Add media", exact=True).last
        media_button.evaluate("(el) => el.click()")
        file_input = page.locator('input[type="file"]').last
        file_input.wait_for(state="attached", timeout=20_000)
        file_input.set_input_files([item["path"] for item in files[:5]], timeout=60_000)
        next_button = page.get_by_role("button", name="Next", exact=True).last
        _wait_until_enabled(next_button, 30_000)
        next_button.evaluate("(el) => el.click()")
        if context_text:
            _ensure_linkedin_caption(page, context_text)
        _capture(job_id, page)

    _update(job_id, message="Finalizing the confirmed LinkedIn post", step=4)
    post_button = page.get_by_role("button", name="Post", exact=True).last
    _wait_until_enabled(post_button, 30_000)
    post_button.evaluate("(el) => el.click()")
    editor.wait_for(state="hidden", timeout=30_000)
    _capture(job_id, page)

    expected = " ".join(context_text.split())[:90]
    verified = False
    evidence = ""
    success_confirmation_seen = False
    recent_post_found = False
    for attempt in range(4):
        try:
            page.wait_for_timeout(1500 if attempt == 0 else 2500)
            visible = " ".join(page.locator("body").inner_text(timeout=10_000).split())
            if re.search(r"\b(?:post (?:was )?(?:successful|published)|your post is live|view post)\b", visible, re.I):
                success_confirmation_seen = True
            if profile_activity_url:
                page.goto(profile_activity_url, wait_until="commit", timeout=60_000)
                page.wait_for_timeout(3500)
                raw_activity = page.locator("body").inner_text(timeout=10_000)
                activity_text = " ".join(raw_activity.split())
                first_post = activity_text
                first_marker = activity_text.find("Feed post number 1")
                second_marker = activity_text.find("Feed post number 2")
                if first_marker >= 0:
                    first_post = activity_text[first_marker:second_marker if second_marker > first_marker else None]
                recent_post = bool(re.search(r"\b(?:now|just now|\d{1,2}\s*(?:s|sec|secs|m|min|mins|minute|minutes))\b", first_post, re.I))
                recent_post_found = recent_post_found or recent_post
                if not context_text and recent_post and success_confirmation_seen:
                    verified = True
                    evidence = "The confirmed media-only post is visible in LinkedIn Recent Activity."
                    break
                if expected and expected in first_post and recent_post:
                    verified = True
                    evidence = "The approved caption is visible in LinkedIn Recent Activity."
                    break
                page.reload(wait_until="commit", timeout=60_000)
        except Exception:
            continue
    if not verified and context_text and success_confirmation_seen and profile_activity_url and recent_post_found:
        try:
            _update(job_id, status="running", message="Restoring the approved caption to the new LinkedIn post", current_url=page.url, step=5)
            repair_latest_linkedin_caption(page, profile_activity_url, context_text)
            page.goto(profile_activity_url, wait_until="commit", timeout=60_000)
            page.wait_for_timeout(3500)
            repaired = " ".join(page.locator("body").inner_text(timeout=10_000).split())
            if expected and expected in repaired:
                verified = True
                evidence = "LinkedIn dropped the caption during media upload; E.D.I.T.H. restored and verified it on the published post."
                _capture(job_id, page)
        except Exception as repair_error:
            _update(job_id, repair_error=str(repair_error)[:800])
    if not verified:
        _update(
            job_id,
            status="waiting_for_user",
            message="LinkedIn closed the composer, but E.D.I.T.H. could not verify that the approved caption was published. Check Recent Activity before retrying to avoid a duplicate post.",
            current_url=page.url,
            step=5,
            result={"evidence": "Publish result could not be independently verified.", "url": page.url},
        )
        return True
    _update(
        job_id,
        status="completed",
        message="LinkedIn post published",
        current_url=page.url,
        step=5,
        result={"evidence": evidence, "url": page.url},
    )
    return True


def repair_latest_linkedin_caption(page: Any, activity_url: str, caption: str) -> None:
    """Recovery helper for a just-created LinkedIn image post whose caption was not committed."""
    page.goto(activity_url, wait_until="commit", timeout=90_000)
    page.wait_for_timeout(8_000)
    menu = page.get_by_role("button", name=re.compile(r"Open control menu for post", re.I)).first
    menu.wait_for(state="visible", timeout=30_000)
    _unblock_click_target(menu)
    menu.click(timeout=20_000)

    edit = page.get_by_text("Edit post", exact=True).last
    edit.wait_for(state="visible", timeout=15_000)
    _unblock_click_target(edit)
    edit.click(timeout=20_000)

    editor = page.get_by_label("Text editor for creating content", exact=True).last
    editor.wait_for(state="visible", timeout=20_000)
    editor.evaluate("(el) => el.focus()")
    page.keyboard.press("Control+A")
    page.keyboard.insert_text(caption)

    save = page.get_by_role("button", name="Save", exact=True).last
    _wait_until_enabled(save, 30_000)
    save.evaluate("(el) => el.click()")
    editor.wait_for(state="hidden", timeout=30_000)


def run(job_id: str) -> None:
    payload = _read(job_id)
    task = payload["task"]
    if not GROQ_API_KEYS:
        _update(job_id, status="failed", message="Universal Browser needs a GROQ_API_KEY", error="GROQ_API_KEY missing")
        return
    executable = _browser_executable()
    if not executable:
        _update(job_id, status="failed", message="Edge or Chrome was not found", error="No supported browser executable")
        return
    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    _update(job_id, status="running", message="Opening the universal browser")
    history: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        launch_options: dict[str, Any] = {
            "executable_path": executable,
            "headless": HEADLESS,
            "args": ["--disable-blink-features=AutomationControlled", "--disable-quic"],
        }
        if HEADLESS:
            launch_options["viewport"] = {"width": 1280, "height": 820}
        else:
            launch_options["no_viewport"] = True
            left, top, width, height = _native_window_geometry()
            launch_options["args"].extend([
                f"--window-position={left},{top}",
                f"--window-size={width},{height}",
                "--no-first-run",
                "--no-default-browser-check",
            ])
        context = playwright.chromium.launch_persistent_context(str(PROFILE_DIR), **launch_options)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            _update(job_id, message="Browser opened beside E.D.I.T.H. · you can click and type directly")
            page.goto(task["url"], wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2500)
            _capture(job_id, page)
            if task.get("action_type") == "navigate":
                _update(
                    job_id,
                    status="completed",
                    message=f"Opened {page.title() or task['url']}",
                    current_url=page.url,
                    result={"evidence": f"Opened {page.title() or page.url}", "url": page.url},
                )
                return
            if _auth_visible(page):
                page = _wait_for_private_auth(job_id, page)
                if page is None:
                    return
            if _run_linkedin_publish(job_id, page, task):
                return
            for step in range(1, MAX_STEPS + 1):
                if _cancelled(job_id):
                    return
                if _auth_visible(page):
                    page = _wait_for_private_auth(job_id, page)
                    if page is None:
                        return
                is_linkedin = "linkedin.com" in page.url.lower() and task.get("action_type") in {"publish", "post", "upload"}
                state = _page_state(page, annotate=not is_linkedin)
                _update(job_id, status="running", message=f"Working in browser · step {step}", current_url=page.url, step=step)
                _capture(job_id, page)
                site_action = _linkedin_action(task, state, history) if is_linkedin else None
                action = site_action or ({"action": "wait"} if is_linkedin else _next_action(task, state, history))
                if isinstance(action.get("action"), dict):
                    nested = action["action"]
                    action = {**action, **nested, "action": nested.get("type") or nested.get("action")}
                kind = str(action.get("action") or action.get("type") or "").lower()
                if not kind and "done" in action:
                    kind = "done"
                    action["evidence"] = action.get("evidence") or action.get("done")
                if not kind and "user" in action:
                    kind = "user"
                    action["message"] = action.get("message") or action.get("user")
                history.append(action)
                _update(job_id, last_action=action)
                if kind in {"done", "finish", "complete"}:
                    _update(job_id, status="completed", message="Browser task completed", current_url=page.url, result={"evidence": action.get("evidence", ""), "url": page.url})
                    return
                if kind == "read" and task.get("action_type") == "read":
                    evidence = action.get("evidence") or f"Opened {state['title']} at {state['url']}"
                    _update(job_id, status="completed", message="Browser read completed", current_url=page.url, result={"evidence": evidence, "url": page.url})
                    return
                if kind == "user":
                    request = str(action.get("message") or "User input is required")
                    if re.search(r"\b(?:element id|selector|html|page state|ui detail)\b", request, re.I):
                        history.append({"error": "Never ask the user for browser internals. Click the relevant control and inspect the next state."})
                        page.wait_for_timeout(900)
                        continue
                    _update(job_id, status="waiting_for_user", message=request, current_url=page.url)
                    return
                if kind == "wait":
                    page.wait_for_timeout(1500)
                    continue
                if not re.fullmatch(r"e\d+", str(action.get("id", ""))):
                    history.append({"error": "Choose one of the supplied element IDs, or return done/user."})
                    continue
                try:
                    if _execute_linkedin_action(page, task, action):
                        pass
                    elif kind == "click":
                        locator = _locator(page, action.get("id", ""))
                        locator.click(timeout=15_000)
                    elif kind == "fill":
                        locator = _locator(page, action.get("id", ""))
                        input_type = (locator.get_attribute("type") or "").lower()
                        if input_type in {"password"}:
                            page = _wait_for_private_auth(job_id, page)
                            if page is None:
                                return
                        else:
                            locator.fill(str(action.get("value", "")), timeout=15_000)
                    elif kind == "upload":
                        locator = _locator(page, action.get("id", ""))
                        files = task.get("files", [])
                        index = int(action.get("file_index", 0))
                        if not (0 <= index < len(files)):
                            raise ValueError("Requested attachment is unavailable")
                        locator.set_input_files(files[index]["path"], timeout=30_000)
                    elif kind == "select":
                        locator = _locator(page, action.get("id", ""))
                        locator.select_option(str(action.get("value", "")), timeout=15_000)
                    elif kind == "press":
                        locator = _locator(page, action.get("id", ""))
                        locator.press(str(action.get("key", "Enter")), timeout=15_000)
                    else:
                        raise ValueError(f"Unsupported browser action: {kind}")
                except Exception as action_error:
                    detail = str(action_error).lower()
                    if any(marker in detail for marker in ("detached from the dom", "not attached", "timeout", "intercepts pointer events")):
                        history.append({"error": "The page re-rendered during the action. Re-scan and retry the control.", "detail": str(action_error)[:400]})
                        _update(
                            job_id,
                            message=f"Page changed during {action.get('_intent') or kind}; re-scanning",
                            transient_error=str(action_error)[:800],
                            current_url=page.url,
                        )
                        page.wait_for_timeout(1000)
                        continue
                    raise
                action["_executed"] = True
                _update(job_id, last_action=action)
                page.wait_for_timeout(900)
                _capture(job_id, page)
            _update(job_id, status="failed", message="Browser workflow reached its step limit", error="Step limit reached", current_url=page.url)
        except Exception as exc:
            _capture(job_id, page)
            _update(job_id, status="failed", message="Universal Browser could not complete the task", error=str(exc), current_url=getattr(page, "url", ""))
        finally:
            context.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.services.universal_browser_worker JOB_ID")
    with _exclusive_browser(sys.argv[1]) as acquired:
        if acquired:
            run(sys.argv[1])
