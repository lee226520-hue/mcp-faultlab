"""Deterministic fault rules and response mutations."""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass
from typing import Any

from .protocol import request_label, tool_name


SUPPORTED_FAULTS = ("timeout", "tool_error", "stale_data", "server_error", "drop")


@dataclass(frozen=True)
class FaultRule:
    """A fault to apply to one matching request occurrence."""

    kind: str
    method: str | None = None
    tool: str | None = None
    occurrence: int | None = 1
    delay_ms: int = 1500
    message: str = "Injected by mcp-faultlab"
    replacement: str = "STALE_DATA"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FaultRule":
        kind = str(data.get("kind", "tool_error"))
        if kind not in SUPPORTED_FAULTS:
            raise ValueError(f"Unknown fault kind {kind!r}; use {', '.join(SUPPORTED_FAULTS)}")
        occurrence: int | None
        if data.get("every") is True or data.get("occurrence") == "all":
            occurrence = None
        else:
            occurrence = int(data.get("occurrence", 1))
        return cls(
            kind=kind,
            method=data.get("method"),
            tool=data.get("tool"),
            occurrence=occurrence,
            delay_ms=max(0, int(data.get("delay_ms", 1500))),
            message=str(data.get("message", "Injected by mcp-faultlab")),
            replacement=str(data.get("replacement", "STALE_DATA")),
        )

    def matches(self, message: dict[str, Any], count: int) -> bool:
        method = message.get("method")
        tool = tool_name(message)
        if self.method is not None and self.method != method:
            return False
        if self.tool is not None and self.tool != tool:
            return False
        return self.occurrence is None or count == self.occurrence

    def mutate(self, response: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(response)
        if self.kind == "timeout":
            time.sleep(self.delay_ms / 1000)
            return result
        if self.kind == "drop":
            raise DropResponse
        if self.kind == "tool_error":
            result.pop("error", None)
            result["result"] = {
                "isError": True,
                "content": [{"type": "text", "text": self.message}],
            }
            return result
        if self.kind == "server_error":
            result.pop("result", None)
            result["error"] = {"code": -32000, "message": self.message}
            return result
        if self.kind == "stale_data":
            payload = result.setdefault("result", {})
            payload["isError"] = False
            payload["content"] = [{"type": "text", "text": self.replacement}]
            return result
        raise ValueError(f"Unsupported fault kind: {self.kind}")


class DropResponse(Exception):
    """Internal signal that the proxy should not deliver a response."""


class FaultEngine:
    def __init__(self, rules: list[FaultRule] | None = None):
        self.rules = rules or []
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def observe(self, message: dict[str, Any]) -> list[FaultRule]:
        with self._lock:
            label = request_label(message)
            self._counts[label] = self._counts.get(label, 0) + 1
            count = self._counts[label]
            return [rule for rule in self.rules if rule.matches(message, count)]


# v0.1 compatibility: callers that imported Fault still get the richer rule.
Fault = FaultRule


def parse_rules(data: Any) -> list[FaultRule]:
    """Accept a single rule, a list, or {"faults": [...]} config."""

    if isinstance(data, dict) and "faults" in data:
        data = data["faults"]
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("Fault config must be an object, an array, or an object with faults")
    return [FaultRule.from_dict(item) for item in data]
