"""Generate deterministic fault variants from a recorded cassette."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from .cassette import load, save
from .faults import DropResponse, FaultEngine, FaultRule, parse_rules
from .protocol import is_request, is_response


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-").lower() or "case"


def apply_rules(cassette: dict[str, Any], rules: list[FaultRule]) -> dict[str, Any]:
    result = copy.deepcopy(cassette)
    engine = FaultEngine(rules)
    pending: dict[Any, list[FaultRule]] = {}
    for event in result["events"]:
        message = event.get("message", {})
        if event.get("direction") == "client->server" and is_request(message) and "id" in message:
            pending[event.get("request_sequence")] = engine.observe(message)
        elif event.get("direction") == "server->client" and is_response(message):
            selected = pending.get(event.get("request_sequence"), [])
            if not selected:
                continue
            original = copy.deepcopy(message)
            delivered: dict[str, Any] | None = message
            kinds = []
            for rule in selected:
                kinds.append(rule.kind)
                try:
                    delivered = rule.mutate(delivered) if delivered is not None else None
                except DropResponse:
                    delivered = None
                    break
            event["message_before_fault"] = original
            event["fault"] = "+".join(kinds)
            if delivered is None:
                event["message"] = {"dropped": True, "request_id": message.get("id")}
            else:
                event["message"] = delivered
    return result


def write_campaign(cassette_path: str, config: Any, out_dir: str) -> list[Path]:
    source = load(cassette_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if isinstance(config, dict) and "cases" in config:
        cases = config["cases"]
    elif isinstance(config, list):
        cases = [{"name": f"case-{index + 1}", "faults": [item]} for index, item in enumerate(config)]
    else:
        cases = [{"name": "case-1", "faults": config}]
    paths = []
    for index, case in enumerate(cases, start=1):
        name = str(case.get("name", f"case-{index}"))
        rules = parse_rules(case.get("faults", case))
        variant = apply_rules(source, rules)
        variant.setdefault("metadata", {})["campaign"] = name
        path = out / f"{index:03d}-{_safe_name(name)}.json"
        save(path, variant)
        paths.append(path)
    return paths

