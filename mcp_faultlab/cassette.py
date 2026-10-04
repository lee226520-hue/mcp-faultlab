"""Versioned cassette persistence, redaction, and inspection."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .redaction import redact


FORMAT = "mcp-faultlab/v1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_cassette(target: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "recorded_at": now(),
        "target": target,
        "metadata": metadata or {},
        "events": [],
    }


def add_event(
    cassette: dict[str, Any],
    direction: str,
    message: dict[str, Any],
    *,
    sequence: int | None = None,
    request_id: Any = None,
    **extra: Any,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "sequence": sequence if sequence is not None else len(cassette["events"]) + 1,
        "direction": direction,
        "message": redact(message),
        "at": now(),
    }
    if request_id is not None:
        event["request_id"] = request_id
    event.update({key: redact(value) for key, value in extra.items()})
    cassette["events"].append(event)
    return event


def save(path: str | Path, cassette: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(cassette, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(target)


def load(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise ValueError(f"Unsupported cassette format: {data.get('format')!r}")
    if not isinstance(data.get("events"), list):
        raise ValueError("Cassette must contain an events array")
    return data


def summary(cassette: dict[str, Any]) -> str:
    events = cassette["events"]
    requests = [e for e in events if e["direction"] == "client->server"]
    responses = [e for e in events if e["direction"] == "server->client"]
    faults = [e for e in events if e.get("fault")]
    tools = sorted(
        {
            e["message"].get("params", {}).get("name")
            for e in requests
            if e["message"].get("method") == "tools/call"
            and isinstance(e["message"].get("params"), dict)
            and e["message"].get("params", {}).get("name")
        }
    )
    lines = [
        f"format: {cassette['format']}",
        f"target: {cassette.get('target', '')}",
        f"events: {len(events)} ({len(requests)} requests, {len(responses)} responses)",
        f"tools: {', '.join(tools) if tools else '-'}",
        f"faults: {len(faults)}",
    ]
    for event in faults:
        lines.append(f"- {event['fault']} on sequence {event.get('request_sequence', '?')}")
    return "\n".join(lines)
