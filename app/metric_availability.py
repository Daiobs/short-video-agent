from __future__ import annotations

from collections.abc import Mapping
from typing import Any


METRIC_AVAILABILITY_KEYS = (
    "like_count",
    "comment_count",
    "share_count",
    "collect_count",
)

DEFAULT_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "like_count": ("like_count",),
    "comment_count": ("comment_count",),
    "share_count": ("share_count",),
    "collect_count": ("collect_count",),
}

PUBLIC_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "like_count": ("like_count", "likes", "digg_count", "statistics.digg_count", "点赞"),
    "comment_count": ("comment_count", "comments", "statistics.comment_count", "评论"),
    "share_count": ("share_count", "shares", "statistics.share_count", "分享"),
    "collect_count": ("collect_count", "collects", "statistics.collect_count", "收藏"),
}


def sanitize_metric_availability(value: Any) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: _coerce_bool(value[key])
        for key in METRIC_AVAILABILITY_KEYS
        if key in value
    }


def metric_availability_from_mapping(
    value: Mapping[str, Any] | None,
    aliases: Mapping[str, tuple[str, ...]] | None = None,
) -> dict[str, bool]:
    payload = value if isinstance(value, Mapping) else {}
    explicit = sanitize_metric_availability(payload.get("metric_availability"))
    field_aliases = aliases or DEFAULT_METRIC_ALIASES
    return {
        key: explicit[key]
        if key in explicit
        else any(mapping_path_present(payload, path) for path in field_aliases.get(key, (key,)))
        for key in METRIC_AVAILABILITY_KEYS
    }


def unavailable_metric_availability() -> dict[str, bool]:
    return {key: False for key in METRIC_AVAILABILITY_KEYS}


def metric_availability_state(sample: Any, key: str) -> bool | None:
    if key not in METRIC_AVAILABILITY_KEYS:
        return None
    candidates: list[Any] = []
    if isinstance(sample, Mapping):
        candidates.append(sample.get("metric_availability"))
        raw = sample.get("raw")
    else:
        candidates.append(getattr(sample, "metric_availability", None))
        raw = getattr(sample, "raw", None)
    if isinstance(raw, Mapping):
        candidates.append(raw.get("metric_availability"))
    for candidate in candidates:
        availability = sanitize_metric_availability(candidate)
        if key in availability:
            return availability[key]
    return None


def mapping_path_present(value: Mapping[str, Any] | None, path: str) -> bool:
    if isinstance(value, Mapping) and path in value:
        return True
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    return True


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "no", "off"}:
            return False
        if normalized in {"1", "true", "yes", "on"}:
            return True
    return bool(value)
