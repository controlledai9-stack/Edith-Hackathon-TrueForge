"""
Compares two structured snapshots (never raw HTML) and produces a list of
change records. Used by watchlist_service after every scan to detect what
actually changed for an entity/category.
"""
import difflib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- Normalization helpers ----------

def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def normalize_text_casing(s: str) -> str:
    return normalize_whitespace(s).lower()


def normalize_currency(value) -> Optional[float]:
    """Extract a numeric value from strings like '$1,299.00', '₹899', '999'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value)
    s = re.sub(r"[^\d.\-]", "", s)
    if not s or s in ("-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def normalize_url(u: str) -> str:
    if not u:
        return ""
    u = u.strip().rstrip("/")
    u = re.sub(r"^https?://(www\.)?", "", u, flags=re.I)
    return u.lower()


def normalize_timestamp(ts: str) -> str:
    return (ts or "").strip()


def looks_numeric(value) -> bool:
    return normalize_currency(value) is not None


def dedupe_items(items: List[dict], key_field: Optional[str] = None) -> List[dict]:
    seen = set()
    out = []
    for item in items:
        k = item.get(key_field) if key_field and isinstance(item, dict) else str(item)
        k = normalize_text_casing(str(k))
        if k in seen:
            continue
        seen.add(k)
        out.append(item)
    return out


# ---------- Core comparison ----------

def _values_equal(a, b) -> bool:
    if looks_numeric(a) and looks_numeric(b):
        return abs(normalize_currency(a) - normalize_currency(b)) < 1e-9
    if isinstance(a, str) or isinstance(b, str):
        return normalize_text_casing(str(a)) == normalize_text_casing(str(b))
    return a == b


def _record_key(record: dict) -> str:
    if "url" in record and record["url"]:
        return normalize_url(str(record["url"]))
    for candidate in ("id", "name", "title", "product", "sku"):
        if candidate in record and record[candidate]:
            return normalize_text_casing(str(record[candidate]))
    return normalize_text_casing(str(sorted(record.items())))


def compare_dicts(entity: str, field_prefix: str, before: dict, after: dict) -> List[dict]:
    changes = []
    before = before or {}
    after = after or {}
    all_keys = set(before.keys()) | set(after.keys())

    for key in sorted(all_keys):
        b_val = before.get(key)
        a_val = after.get(key)
        field_name = f"{field_prefix}.{key}" if field_prefix else key

        if key not in before:
            changes.append({
                "change_type": "field_added", "entity": entity, "field": field_name,
                "before": None, "after": a_val, "detected_at": _now_iso(),
            })
            continue
        if key not in after:
            changes.append({
                "change_type": "field_removed", "entity": entity, "field": field_name,
                "before": b_val, "after": None, "detected_at": _now_iso(),
            })
            continue
        if _values_equal(b_val, a_val):
            continue

        if looks_numeric(b_val) and looks_numeric(a_val):
            bn, an = normalize_currency(b_val), normalize_currency(a_val)
            abs_change = an - bn
            pct_change = (abs_change / bn * 100) if bn else None
            changes.append({
                "change_type": "price_change" if "price" in key.lower() else "value_change",
                "entity": entity, "field": field_name,
                "before": bn, "after": an,
                "absolute_change": round(abs_change, 4),
                "percentage_change": round(pct_change, 2) if pct_change is not None else None,
                "detected_at": _now_iso(),
            })
        else:
            changes.append({
                "change_type": "text_change", "entity": entity, "field": field_name,
                "before": b_val, "after": a_val, "detected_at": _now_iso(),
            })
    return changes


def compare_lists(entity: str, field_prefix: str, before: list, after: list) -> List[dict]:
    changes = []
    key_field = None
    if before and isinstance(before[0], dict):
        for candidate in ("id", "name", "title", "product", "sku"):
            if candidate in before[0]:
                key_field = candidate
                break

    before = dedupe_items(before or [], key_field) if (before and isinstance(before[0], dict)) else (before or [])
    after = dedupe_items(after or [], key_field) if (after and isinstance(after[0], dict)) else (after or [])

    before_keyed = {_record_key(b) if isinstance(b, dict) else str(b): b for b in before}
    after_keyed = {_record_key(a) if isinstance(a, dict) else str(a): a for a in after}

    added = [after_keyed[k] for k in after_keyed if k not in before_keyed]
    removed = [before_keyed[k] for k in before_keyed if k not in after_keyed]
    common = [k for k in after_keyed if k in before_keyed]

    for item in added:
        label = item.get(key_field) if key_field and isinstance(item, dict) else item
        changes.append({
            "change_type": "item_added", "entity": entity, "field": field_prefix,
            "before": None, "after": label, "detected_at": _now_iso(),
        })
    for item in removed:
        label = item.get(key_field) if key_field and isinstance(item, dict) else item
        changes.append({
            "change_type": "item_removed", "entity": entity, "field": field_prefix,
            "before": label, "after": None, "detected_at": _now_iso(),
        })
    for k in common:
        b_item, a_item = before_keyed[k], after_keyed[k]
        if isinstance(b_item, dict) and isinstance(a_item, dict):
            changes.extend(compare_dicts(entity, field_prefix, b_item, a_item))
        elif not _values_equal(b_item, a_item):
            changes.append({
                "change_type": "value_change", "entity": entity, "field": field_prefix,
                "before": b_item, "after": a_item, "detected_at": _now_iso(),
            })

    if len(before or []) and abs(len(after or []) - len(before or [])) / max(len(before), 1) > 0.3:
        changes.append({
            "change_type": "item_count_shift", "entity": entity, "field": field_prefix,
            "before": len(before), "after": len(after),
            "absolute_change": len(after) - len(before), "detected_at": _now_iso(),
        })
    return changes


def compare_snapshots(entity: str, before_data: Any, after_data: Any) -> List[dict]:
    """Entry point: compares normalized structured data (dict, list, or
    plain text) and returns a list of change records. Returns [] when the
    two snapshots are effectively equivalent."""
    if before_data is None or after_data is None:
        return []

    if isinstance(before_data, dict) and isinstance(after_data, dict):
        return compare_dicts(entity, "", before_data, after_data)
    if isinstance(before_data, list) and isinstance(after_data, list):
        return compare_lists(entity, "records", before_data, after_data)

    # Fallback: plain text comparison from direct webpage extraction —
    # no field-level diff possible, just report whether it changed at all.
    before_text = normalize_whitespace(str(before_data))
    after_text = normalize_whitespace(str(after_data))
    if before_text == after_text:
        return []
    return [{
        "change_type": "text_change", "entity": entity, "field": "page_text",
        "before": before_text[:300], "after": after_text[:300],
        "detected_at": _now_iso(),
    }]


# ---------- User-facing reports ----------

def _short_value(value: Any, limit: int = 110) -> str:
    if value is None:
        return "not present"
    text = normalize_whitespace(str(value))
    if len(text) <= limit:
        return text
    return text[:limit - 1].rstrip() + "…"


def _text_diff_fragments(before: Any, after: Any, limit: int = 5) -> List[str]:
    """Extract compact, exact changed fragments from long page text."""
    before_words = re.findall(r"\S+", str(before or ""))
    after_words = re.findall(r"\S+", str(after or ""))
    matcher = difflib.SequenceMatcher(a=before_words, b=after_words, autojunk=False)
    fragments = []
    for operation, i1, i2, j1, j2 in matcher.get_opcodes():
        if operation == "equal":
            continue
        old = _short_value(" ".join(before_words[i1:i2]), 70)
        new = _short_value(" ".join(after_words[j1:j2]), 70)
        if operation == "insert":
            fragments.append(f"added “{new}”")
        elif operation == "delete":
            fragments.append(f"removed “{old}”")
        else:
            fragments.append(f"“{old}” → “{new}”")
        if len(fragments) >= limit:
            break
    return fragments


def summarize_change(change: dict) -> str:
    """Create an evidence-only description of one structured change."""
    change_type = change.get("change_type") or "change"
    field = change.get("field") or "data"
    before, after = change.get("before"), change.get("after")

    if change_type == "item_added":
        detail = f"Added {_short_value(after)} to {field}."
    elif change_type == "item_removed":
        detail = f"Removed {_short_value(before)} from {field}."
    elif change_type == "field_added":
        detail = f"New field {field}: {_short_value(after)}."
    elif change_type == "field_removed":
        detail = f"Removed field {field}; previous value was {_short_value(before)}."
    elif change_type == "item_count_shift":
        detail = f"{field} count changed from {_short_value(before)} to {_short_value(after)}."
    elif change_type in ("value_change", "price_change"):
        detail = f"{field} changed from {_short_value(before)} to {_short_value(after)}"
        if change.get("percentage_change") is not None:
            pct = change["percentage_change"]
            detail += f" ({pct:+g}%)"
        detail += "."
    elif change_type == "text_change":
        fragments = _text_diff_fragments(before, after)
        detail = (f"{field} changed: " + "; ".join(fragments) + ".") if fragments else \
            f"{field} changed from {_short_value(before)} to {_short_value(after)}."
    else:
        detail = f"{field} changed from {_short_value(before)} to {_short_value(after)}."
    return detail


def format_scan_change_report(scan_results: List[dict], max_changes: int = 20) -> str:
    """Turn a completed watchlist scan into an immediate factual report."""
    changes = []
    for entity_result in scan_results or []:
        entity = entity_result.get("entity") or "Unknown entity"
        for category_result in entity_result.get("results", []):
            category = category_result.get("category") or "uncategorized"
            for raw_change in category_result.get("changes", []):
                changes.append({**raw_change, "entity": raw_change.get("entity") or entity,
                                "category": raw_change.get("category") or category})

    entity_count = len(scan_results or [])
    if not changes:
        return f"Scanned {entity_count} watchlist entit{'y' if entity_count == 1 else 'ies'} — no changes detected."

    lines = [
        f"Scanned {entity_count} watchlist entit{'y' if entity_count == 1 else 'ies'} — "
        f"{len(changes)} change{'s' if len(changes) != 1 else ''} detected:",
    ]
    for index, change in enumerate(changes[:max_changes], 1):
        lines.append(f"{index}. {change['entity']} · {change['category']}")
        lines.append(f"   {summarize_change(change)}")
        if change.get("source_url"):
            lines.append(f"   Source: {change['source_url']}")
    if len(changes) > max_changes:
        lines.append(f"Plus {len(changes) - max_changes} additional recorded changes.")
    return "\n".join(lines)
