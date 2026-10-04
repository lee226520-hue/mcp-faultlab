"""Serve a recorded cassette as a read-only MCP stdio mock."""

from __future__ import annotations

import sys
from typing import Any, TextIO

from .cassette import load
from .protocol import decode, encode, tool_name


def _same_request(recorded: dict[str, Any], incoming: dict[str, Any]) -> bool:
    if recorded.get("method") != incoming.get("method"):
        return False
    recorded_tool = tool_name(recorded)
    incoming_tool = tool_name(incoming)
    if recorded_tool or incoming_tool:
        return recorded_tool == incoming_tool
    return True


def serve(path: str, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
    cassette = load(path)
    events = cassette["events"]
    cursor = 0
    for raw in stdin:
        incoming = decode(raw)
        if incoming is None:
            continue
        while cursor < len(events) and events[cursor]["direction"] != "client->server":
            cursor += 1
        if cursor >= len(events):
            raise RuntimeError("replay exhausted: no recorded request matches incoming message")
        recorded_request = events[cursor]["message"]
        if not _same_request(recorded_request, incoming):
            raise RuntimeError(
                f"replay divergence: expected {recorded_request.get('method')!r}, "
                f"got {incoming.get('method')!r}"
            )
        request_event = events[cursor]
        request_sequence = request_event.get("request_sequence")
        recorded_id = recorded_request.get("id")
        cursor += 1
        response_event = None
        # Preserve server notifications in their original position, then find
        # the response associated with this request.  A response is linked by
        # request_sequence in faultlab cassettes; old cassettes fall back to id.
        while cursor < len(events) and events[cursor]["direction"] != "client->server":
            event = events[cursor]
            if event["direction"] == "server->client":
                message = event["message"]
                linked = (
                    request_sequence is not None
                    and event.get("request_sequence") == request_sequence
                ) or (request_sequence is None and message.get("id") == recorded_id)
                if linked and response_event is None:
                    response_event = event
                elif not linked and "id" not in message:
                    stdout.write(encode(message) + "\n")
                    stdout.flush()
            cursor += 1
        if "id" not in incoming:
            continue
        if response_event is None:
            raise RuntimeError("replay exhausted: recorded request has no response")
        response = dict(response_event["message"])
        if response.get("dropped"):
            continue
        if "id" in response:
            response["id"] = incoming["id"]
        stdout.write(encode(response) + "\n")
        stdout.flush()
    return 0
