"""JSON-RPC helpers for MCP stdio transport."""

from __future__ import annotations

import json
from typing import Any


def decode(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError("MCP messages must be JSON objects")
    return value


def encode(message: dict[str, Any]) -> str:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":"))


def id_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def message_id(message: dict[str, Any]) -> Any:
    return message.get("id")


def has_id(message: dict[str, Any]) -> bool:
    return "id" in message


def is_response(message: dict[str, Any]) -> bool:
    return has_id(message) and ("result" in message or "error" in message) and "method" not in message


def is_request(message: dict[str, Any]) -> bool:
    return isinstance(message.get("method"), str)


def tool_name(message: dict[str, Any]) -> str | None:
    if message.get("method") != "tools/call":
        return None
    params = message.get("params")
    if isinstance(params, dict) and isinstance(params.get("name"), str):
        return params["name"]
    return None


def request_label(message: dict[str, Any]) -> str:
    tool = tool_name(message)
    if tool:
        return f"tools/call:{tool}"
    return str(message.get("method", "notification"))

