"""Deterministic field normalization without factual guessing."""

import json
import re
from datetime import date, datetime
from typing import Any


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value).strip())
    return text or None


def _normalize_integer(value: Any) -> int | str | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = _normalize_text(value)
    if text is not None and re.fullmatch(r"\d+", text):
        return int(text)
    return text


def _normalize_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _normalize_text(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return text


def _normalize_specifications(value: Any) -> str | None:
    text = _normalize_text(value)
    if text is None:
        return None
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return text
    if isinstance(parsed, (dict, list)):
        return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return text


def normalize_product_sku(raw_data: dict[str, Any]) -> dict[str, Any]:
    normalized = {key: _normalize_text(value) for key, value in raw_data.items()}
    platform = normalized.get("platform")
    normalized["platform"] = platform.lower() if platform else None
    normalized["applicable_age_min"] = _normalize_integer(raw_data.get("applicable_age_min"))
    normalized["applicable_age_max"] = _normalize_integer(raw_data.get("applicable_age_max"))
    normalized["effective_from"] = _normalize_date(raw_data.get("effective_from"))
    normalized["effective_to"] = _normalize_date(raw_data.get("effective_to"))
    normalized["specifications"] = _normalize_specifications(raw_data.get("specifications"))
    return normalized
