"""
Watchlist manager — the core of the monitoring system. Not hardcoded to any
company/industry: any entity name + category list works. Source URLs are
discovered via Tavily on first scan and cached; the direct webpage reader
does the actual extraction.
"""
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from config import WATCHLISTS_FILE, TAVILY_API_KEY, MONITORING_HISTORY_DIR
from app.services.scraper_service import get_scraper_service, expected_fields_for
from app.services.change_detection_service import compare_snapshots

logger = logging.getLogger("EDITH")

DEFAULT_CATEGORIES = ["news"]
_MAX_MONITORING_HISTORY = 100


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in (s or "").strip().lower()).strip("-") or "entity"


def _tavily_client():
    if not TAVILY_API_KEY:
        return None
    try:
        from tavily import TavilyClient
        return TavilyClient(api_key=TAVILY_API_KEY)
    except Exception as e:
        logger.warning("[WATCHLIST] Tavily unavailable: %s", e)
        return None


def discover_source_url(entity: str, category: str) -> Optional[str]:
    """Uses Tavily to find the most likely official/public page for a given
    entity + category (e.g. 'NVIDIA' + 'pricing' -> NVIDIA's pricing page)."""
    client = _tavily_client()
    if not client:
        return None
    query = f"{entity} official {category} page"
    try:
        resp = client.search(query=query, max_results=3, include_answer=False)
        results = resp.get("results", [])
        return results[0]["url"] if results else None
    except Exception as e:
        logger.warning("[WATCHLIST] Source discovery failed for %s/%s: %s", entity, category, e)
        return None


class WatchlistService:
    def __init__(self):
        # CRUD methods also append to the monitoring history.  A regular Lock
        # deadlocks when add/remove holds it and _log_history acquires it again,
        # which in turn blocks FastAPI's event loop and makes every dashboard
        # endpoint appear to load forever.  The operations are intentionally
        # nested, so use a re-entrant lock.
        self._lock = threading.RLock()
        self.scraper = get_scraper_service()

    # ---------- Storage ----------

    def _load(self) -> Dict[str, dict]:
        if not WATCHLISTS_FILE.exists():
            return {}
        try:
            return json.loads(WATCHLISTS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("[WATCHLIST] Could not read watchlists.json: %s", e)
            return {}

    def _save(self, watchlists: Dict[str, dict]):
        try:
            WATCHLISTS_FILE.write_text(json.dumps(watchlists, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("[WATCHLIST] Could not persist watchlists.json: %s", e)

    def _log_history(self, event_type: str, payload: dict):
        path = MONITORING_HISTORY_DIR / "events.json"
        with self._lock:
            events = []
            if path.exists():
                try:
                    events = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    events = []
            events.append({"type": event_type, "timestamp": _now_iso(), **payload})
            events = events[-_MAX_MONITORING_HISTORY:]
            try:
                path.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                logger.warning("[WATCHLIST] Could not persist monitoring history: %s", e)

    def get_history(self, limit: int = 50) -> List[dict]:
        path = MONITORING_HISTORY_DIR / "events.json"
        if not path.exists():
            return []
        try:
            events = json.loads(path.read_text(encoding="utf-8"))
            return list(reversed(events))[:limit]
        except Exception:
            return []

    # ---------- CRUD ----------

    def get_watchlists(self) -> List[dict]:
        return list(self._load().values())

    def get_watchlist(self, name_or_id: str) -> Optional[dict]:
        watchlists = self._load()
        if name_or_id in watchlists:
            return watchlists[name_or_id]
        target = _slug(name_or_id)
        for w in watchlists.values():
            if _slug(w["name"]) == target:
                return w
        return None

    def add_watchlist(self, name: str, categories: Optional[List[str]] = None, entity_type: str = "company") -> dict:
        with self._lock:
            watchlists = self._load()
            existing = None
            target = _slug(name)
            for w in watchlists.values():
                if _slug(w["name"]) == target:
                    existing = w
                    break

            categories = categories or DEFAULT_CATEGORIES
            if existing:
                merged = sorted(set(existing.get("categories", [])) | set(categories))
                existing["categories"] = merged
                existing["enabled"] = True
                watchlists[existing["id"]] = existing
                self._save(watchlists)
                self._log_history("watchlist_updated", {"entity": name, "categories": merged})
                return existing

            entry = {
                "id": uuid.uuid4().hex[:10],
                "name": name,
                "type": entity_type,
                "categories": categories,
                "sources": [],  # [{"category": "...", "url": "..."}] — filled in on first scan
                "enabled": True,
                "created_at": _now_iso(),
                "last_scan": None,
            }
            watchlists[entry["id"]] = entry
            self._save(watchlists)
            self._log_history("watchlist_created", {"entity": name, "categories": categories})
            return entry

    def remove_watchlist(self, name_or_id: str, category: Optional[str] = None) -> bool:
        with self._lock:
            watchlists = self._load()
            entry = self.get_watchlist(name_or_id)
            if not entry:
                return False
            if category:
                entry["categories"] = [c for c in entry["categories"] if c != category]
                entry["sources"] = [s for s in entry["sources"] if s.get("category") != category]
                watchlists[entry["id"]] = entry
                self._save(watchlists)
                self._log_history("watchlist_category_removed", {"entity": entry["name"], "category": category})
                if not entry["categories"]:
                    del watchlists[entry["id"]]
                    self._save(watchlists)
                return True
            del watchlists[entry["id"]]
            self._save(watchlists)
            self._log_history("watchlist_removed", {"entity": entry["name"]})
            return True

    def update_watchlist(self, name_or_id: str, **fields) -> Optional[dict]:
        with self._lock:
            watchlists = self._load()
            entry = self.get_watchlist(name_or_id)
            if not entry:
                return None
            entry.update(fields)
            watchlists[entry["id"]] = entry
            self._save(watchlists)
            return entry

    # ---------- Scanning ----------

    def _ensure_source(self, entry: dict, category: str) -> Optional[str]:
        for s in entry.get("sources", []):
            if s.get("category") == category and s.get("url"):
                return s["url"]
        url = discover_source_url(entry["name"], category)
        if url:
            entry.setdefault("sources", []).append({"category": category, "url": url})
        return url

    def run_watchlist_scan(self, name_or_id: str) -> dict:
        """Scans every category for one entity: discovers sources as
        needed, reads the page, diffs against the last snapshot,
        and logs any detected changes."""
        entry = self.get_watchlist(name_or_id)
        if not entry:
            return {"error": f"No watchlist entry for '{name_or_id}'"}

        results = []
        for category in entry["categories"]:
            url = self._ensure_source(entry, category)
            if not url:
                results.append({"category": category, "status": "no_source_found"})
                continue

            previous = self.scraper.get_latest_snapshot(entry["name"], category)
            outcome = self.scraper.scrape_source(
                entry["name"], category, url,
                expected_fields=expected_fields_for(category),
            )
            snapshot = outcome["snapshot"]

            changes = []
            if previous and snapshot.get("status") == "success":
                changes = compare_snapshots(entry["name"], previous.get("data"), snapshot.get("data"))
                if changes:
                    for c in changes:
                        c["category"] = category
                        c["source_url"] = url
                    self._save_changes(entry["name"], category, changes)

            results.append({
                "category": category, "status": snapshot["status"],
                "source": snapshot["scraper_id"], "healed": snapshot["healed"],
                "changes": changes,
            })

        entry["last_scan"] = _now_iso()
        with self._lock:
            watchlists = self._load()
            watchlists[entry["id"]] = entry
            self._save(watchlists)

        self._log_history("scan_completed", {"entity": entry["name"], "categories": len(results)})
        return {"entity": entry["name"], "scanned_at": entry["last_scan"], "results": results}

    def run_all_watchlists(self) -> List[dict]:
        return [self.run_watchlist_scan(w["id"]) for w in self.get_watchlists() if w.get("enabled", True)]

    # ---------- Changes ----------

    def _save_changes(self, entity: str, category: str, changes: List[dict]):
        from config import CHANGES_DIR
        path = CHANGES_DIR / f"{_slug(entity)}__{_slug(category)}.json"
        with self._lock:
            history = []
            if path.exists():
                try:
                    history = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    history = []
            history.extend(changes)
            history = history[-_MAX_MONITORING_HISTORY:]
            try:
                path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                logger.warning("[WATCHLIST] Could not persist changes for %s/%s: %s", entity, category, e)

    def get_recent_changes(self, limit: int = 30) -> List[dict]:
        from config import CHANGES_DIR
        all_changes = []
        for path in CHANGES_DIR.glob("*.json"):
            try:
                all_changes.extend(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        all_changes.sort(key=lambda c: c.get("detected_at", ""), reverse=True)
        return all_changes[:limit]

    def get_watchlist_history(self, name_or_id: str, limit: int = 30) -> dict:
        entry = self.get_watchlist(name_or_id)
        if not entry:
            return {"error": f"No watchlist entry for '{name_or_id}'"}
        history = {}
        for category in entry["categories"]:
            history[category] = {
                "snapshots": self.scraper.get_snapshot_history(entry["name"], category)[-limit:],
            }
        return {"entity": entry["name"], "history": history}


_watchlist_service_singleton = None


def get_watchlist_service() -> WatchlistService:
    global _watchlist_service_singleton
    if _watchlist_service_singleton is None:
        _watchlist_service_singleton = WatchlistService()
    return _watchlist_service_singleton
