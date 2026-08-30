"""
Wraps the free direct webpage reader with:
  - snapshot persistence (data/snapshots/<entity>__<category>.json)
  - a source health board (data/scraper_health.json) tracking HEALTHY /
    WARNING / STRUCTURE_CHANGED / EXTRACTION_FAILED / HEALING / RECOVERED
    per (entity, category) source.
"""
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import SNAPSHOTS_DIR, SCRAPER_HEALTH_FILE
from app.services.web_reader_service import get_web_reader_service

logger = logging.getLogger("EDITH")

_MAX_SNAPSHOTS_PER_SOURCE = 30
_MAX_HEALTH_HISTORY = 20

STATE_HEALTHY = "HEALTHY"
STATE_WARNING = "WARNING"
STATE_STRUCTURE_CHANGED = "STRUCTURE_CHANGED"
STATE_EXTRACTION_FAILED = "EXTRACTION_FAILED"
STATE_HEALING = "HEALING"
STATE_RECOVERED = "RECOVERED"

# Best-guess expected fields per category, used for structure-change
# detection (a successful scrape that's missing these fields gets flagged
# STRUCTURE_CHANGED rather than treated as healthy). These are generic
# defaults — adjust this map to match the source's actual fields.
CATEGORY_EXPECTED_FIELDS: Dict[str, List[str]] = {
    "pricing": ["price", "plan"],
    "products": ["name", "price"],
    "product launches": ["name"],
    "new releases": ["name", "date"],
    "news": ["title"],
    "news/announcements": ["title"],
    "ai announcements": ["title"],
    "announcements": ["title"],
    "blog": ["title", "date"],
    "changelog": ["version", "date"],
    "changelogs": ["version", "date"],
    "documentation": ["title"],
    "api": ["endpoint"],
    "api pricing": ["price"],
    "api/model updates": ["title"],
    "models": ["name"],
    "features": ["name"],
    "availability": ["status"],
}


def expected_fields_for(category: str) -> Optional[List[str]]:
    return CATEGORY_EXPECTED_FIELDS.get((category or "").strip().lower())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in (s or "").strip().lower()).strip("_") or "unknown"


def _source_key(entity: str, category: str) -> str:
    return f"{_slug(entity)}:{_slug(category)}"


class ScraperService:
    def __init__(self):
        self._lock = threading.Lock()
        self.web_reader = get_web_reader_service()

    # ---------- Snapshots ----------

    def _snapshot_path(self, entity: str, category: str) -> Path:
        return SNAPSHOTS_DIR / f"{_slug(entity)}__{_slug(category)}.json"

    def get_snapshot_history(self, entity: str, category: str) -> List[dict]:
        path = self._snapshot_path(entity, category)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("[SCRAPER] Could not read snapshots for %s/%s: %s", entity, category, e)
            return []

    def get_latest_snapshot(self, entity: str, category: str) -> Optional[dict]:
        history = self.get_snapshot_history(entity, category)
        return history[-1] if history else None

    def _save_snapshot(self, entity: str, category: str, snapshot: dict):
        path = self._snapshot_path(entity, category)
        with self._lock:
            history = self.get_snapshot_history(entity, category)
            history.append(snapshot)
            history = history[-_MAX_SNAPSHOTS_PER_SOURCE:]
            try:
                path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                logger.warning("[SCRAPER] Could not persist snapshot for %s/%s: %s", entity, category, e)

    # ---------- Scraper health board ----------

    def _load_health(self) -> Dict[str, dict]:
        if not SCRAPER_HEALTH_FILE.exists():
            return {}
        try:
            return json.loads(SCRAPER_HEALTH_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("[SCRAPER] Could not read scraper_health.json: %s", e)
            return {}

    def _save_health(self, board: Dict[str, dict]):
        try:
            SCRAPER_HEALTH_FILE.write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("[SCRAPER] Could not persist scraper_health.json: %s", e)

    def get_health_board(self) -> List[dict]:
        board = self._load_health()
        return sorted(board.values(), key=lambda r: r.get("entity", ""))

    def get_health(self, entity: str, category: str) -> Optional[dict]:
        return self._load_health().get(_source_key(entity, category))

    def _record_health(
        self, entity: str, category: str, source_url: str, *,
        state: str, source: str, fields_extracted: int, missing_fields: List[str],
        schema_valid: bool, healed: bool, error: Optional[str],
        detected_by: Optional[str], recovered_by: Optional[str], manual_intervention: bool,
    ):
        with self._lock:
            board = self._load_health()
            key = _source_key(entity, category)
            existing = board.get(key, {})
            previous_state = existing.get("state")

            record = {
                "key": key,
                "entity": entity,
                "category": category,
                "source_url": source_url,
                "state": state,
                "previous_state": previous_state,
                "last_run": _now_iso(),
                "last_success": _now_iso() if state in (STATE_HEALTHY, STATE_RECOVERED) else existing.get("last_success"),
                "fields_extracted": fields_extracted,
                "missing_fields": missing_fields,
                "schema_valid": schema_valid,
                "collector_source": source,
                "healed": healed,
                "error": error,
                "detected_by": detected_by,
                "recovered_by": recovered_by,
                "manual_intervention_required": manual_intervention,
            }
            history = existing.get("history", [])
            history.append({
                "timestamp": record["last_run"], "state": state,
                "source": source, "error": error,
            })
            record["history"] = history[-_MAX_HEALTH_HISTORY:]

            board[key] = record
            self._save_health(board)
            return record

    # ---------- Public: scrape one source with full health tracking ----------

    def scrape_source(
        self, entity: str, category: str, url: str,
        expected_fields: Optional[List[str]] = None,
    ) -> dict:
        """Scrapes one (entity, category) source, saves the snapshot, updates
        the scraper health board, and returns
        {snapshot, health, changed_from_previous}."""
        result = self.web_reader.scrape_with_self_healing(url)

        fields_extracted = 0
        missing_fields: List[str] = []
        schema_valid = True
        data_payload: Any = None

        if result.success:
            if result.source == "scraper_studio" and result.data:
                records = result.data
                data_payload = records
                if records and isinstance(records[0], dict):
                    fields_extracted = len(records[0].keys())
                    if expected_fields:
                        missing_fields = [f for f in expected_fields if f not in records[0] or not records[0].get(f)]
                        schema_valid = len(missing_fields) == 0
            else:
                data_payload = {"text": result.text}
                fields_extracted = 1 if result.text else 0

        snapshot = {
            "entity": entity,
            "category": category,
            "source_url": url,
            "timestamp": _now_iso(),
            "data": data_payload,
            "scraper_id": result.source,
            "status": "success" if result.success else "failed",
            "healed": result.healed,
            "error": result.error,
        }

        # ---- Determine health state (rule-based, technically transparent) ----
        if not result.success:
            state = STATE_EXTRACTION_FAILED
            detected_by, recovered_by, manual = "JARVIS", None, True
        elif result.healed:
            # A compatibility reader reported recovery through a secondary method.
            state = STATE_RECOVERED
            detected_by, recovered_by, manual = "JARVIS", "secondary reader", False
        elif expected_fields and not schema_valid:
            # Scrape succeeded but the expected shape is missing fields —
            # this is schema drift and needs manual attention.
            state = STATE_STRUCTURE_CHANGED
            detected_by, recovered_by, manual = "JARVIS", None, True
        else:
            state = STATE_HEALTHY
            detected_by, recovered_by, manual = None, None, False

        if result.success:
            self._save_snapshot(entity, category, snapshot)

        health = self._record_health(
            entity, category, url,
            state=state, source=result.source, fields_extracted=fields_extracted,
            missing_fields=missing_fields, schema_valid=schema_valid, healed=result.healed,
            error=result.error, detected_by=detected_by, recovered_by=recovered_by,
            manual_intervention=manual,
        )

        return {"snapshot": snapshot, "health": health}


_scraper_service_singleton = None


def get_scraper_service() -> ScraperService:
    global _scraper_service_singleton
    if _scraper_service_singleton is None:
        _scraper_service_singleton = ScraperService()
    return _scraper_service_singleton
