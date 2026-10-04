"""Stable cassette comparison for CI."""

from __future__ import annotations

import json
from typing import Any

from .cassette import load


DEFAULT_IGNORED_KEYS = {
    "at", "sequence", "request_id", "request_sequence", "recorded_at", "target", "id",
    "metadata",
}


def _strip(value: Any, ignored: set[str]) -> Any:
    if isinstance(value, dict):
        return {k: _strip(v, ignored) for k, v in value.items() if k not in ignored}
    if isinstance(value, list):
        return [_strip(item, ignored) for item in value]
    return value


def comparable(cassette: dict[str, Any], ignored: set[str] | None = None) -> list[Any]:
    ignored = DEFAULT_IGNORED_KEYS | (ignored or set())
    result = []
    for event in cassette["events"]:
        result.append(
            {
                "direction": event.get("direction"),
                "message": _strip(event.get("message"), ignored),
            }
        )
    return result


def first_difference(left: Any, right: Any, path: str = "$", ignored: set[str] | None = None) -> str | None:
    if type(left) is not type(right):
        return f"{path}: type {type(left).__name__} != {type(right).__name__}"
    if isinstance(left, dict):
        keys = sorted(set(left) | set(right))
        for key in keys:
            if key not in left:
                return f"{path}.{key}: missing from expected"
            if key not in right:
                return f"{path}.{key}: missing from actual"
            difference = first_difference(left[key], right[key], f"{path}.{key}", ignored)
            if difference:
                return difference
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: length {len(left)} != {len(right)}"
        for index, (a, b) in enumerate(zip(left, right)):
            difference = first_difference(a, b, f"{path}[{index}]", ignored)
            if difference:
                return difference
        return None
    if left != right:
        return f"{path}: {left!r} != {right!r}"
    return None


def compare_paths(expected_path: str, actual_path: str, ignored_keys: set[str] | None = None) -> tuple[bool, str]:
    expected = comparable(load(expected_path), ignored_keys)
    actual = comparable(load(actual_path), ignored_keys)
    difference = first_difference(expected, actual)
    if difference is None:
        return True, "ok: cassettes match"
    return False, difference


def format_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
