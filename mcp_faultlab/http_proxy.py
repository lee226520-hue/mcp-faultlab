"""Small Streamable HTTP JSON proxy for MCP-compatible endpoints.

JSON responses are recorded and faulted. Event-stream responses are forwarded
byte-for-byte and recorded as metadata only; this keeps the proxy honest while
the stdio transport remains the fully deterministic path in v0.2.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from .cassette import add_event, new_cassette, save
from .faults import DropResponse, FaultEngine, FaultRule
from .protocol import is_request


class HTTPProxyState:
    def __init__(self, target_url: str, rules: list[FaultRule] | None, record_path: str | None):
        self.target_url = target_url
        self.engine = FaultEngine(rules)
        self.record_path = record_path
        self.cassette = (
            new_cassette(target_url, metadata={"transport": "streamable-http", "redaction": "automatic"})
            if record_path
            else None
        )
        self._lock = threading.Lock()
        self._sequence = 0

    def next_sequence(self) -> int:
        with self._lock:
            self._sequence += 1
            return self._sequence

    def record(self, direction: str, message: dict[str, Any], **extra: Any) -> None:
        if self.cassette is None:
            return
        with self._lock:
            add_event(
                self.cassette,
                direction,
                message,
                sequence=self._sequence,
                **extra,
            )

    def close(self) -> None:
        if self.cassette is not None and self.record_path:
            save(self.record_path, self.cassette)


def _json_or_raw(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"))
        if isinstance(value, dict):
            return value
        return {"_batch": value}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"_raw": body.decode("utf-8", errors="replace")}


def _apply_rules(response: dict[str, Any], rules: list[FaultRule]) -> tuple[dict[str, Any] | None, str | None]:
    delivered = response
    kind = None
    for rule in rules:
        kind = rule.kind
        try:
            delivered = rule.mutate(delivered)
        except DropResponse:
            return None, kind
    return delivered, kind


def make_handler(state: HTTPProxyState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            request = _json_or_raw(body)
            request_sequence = state.next_sequence()
            selected = state.engine.observe(request) if is_request(request) else []
            state.record("client->server", request, request_sequence=request_sequence)

            headers = {
                key: value
                for key, value in self.headers.items()
                if key.lower() not in {"host", "content-length", "connection"}
            }
            forward = urllib.request.Request(state.target_url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(forward, timeout=60) as upstream:
                    response_body = upstream.read()
                    status = upstream.status
                    response_headers = dict(upstream.headers.items())
            except urllib.error.HTTPError as exc:
                response_body = exc.read()
                status = exc.code
                response_headers = dict(exc.headers.items())
            except (urllib.error.URLError, TimeoutError) as exc:
                payload = {"jsonrpc": "2.0", "error": {"code": -32001, "message": str(exc)}}
                response_body = json.dumps(payload).encode("utf-8")
                status = 502
                response_headers = {"Content-Type": "application/json"}

            content_type = response_headers.get("Content-Type", "")
            if "json" in content_type.lower() or response_body.lstrip().startswith(b"{"):
                original = _json_or_raw(response_body)
                delivered, fault_kind = _apply_rules(original, selected)
                if delivered is None:
                    payload = {"jsonrpc": "2.0", "error": {"code": -32002, "message": "response dropped by mcp-faultlab"}}
                    delivered_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                    status = 504
                    state.record("server->client", {"dropped": True}, request_sequence=request_sequence, fault=fault_kind or "drop", message_before_fault=original)
                else:
                    delivered_body = json.dumps(delivered, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                    extra: dict[str, Any] = {"request_sequence": request_sequence}
                    if fault_kind:
                        extra["fault"] = fault_kind
                        extra["message_before_fault"] = original
                    state.record("server->client", delivered, **extra)
            else:
                delivered_body = response_body
                state.record("server->client", {"_stream": True, "content_type": content_type, "bytes": len(response_body)}, request_sequence=request_sequence)

            self.send_response(status)
            for key, value in response_headers.items():
                if key.lower() not in {"content-length", "transfer-encoding", "connection"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(delivered_body)))
            self.end_headers()
            self.wfile.write(delivered_body)
            self.wfile.flush()

    return Handler


def serve_http(listen: str, target_url: str, rules: list[FaultRule] | None = None, record_path: str | None = None) -> int:
    parsed = urlsplit("//" + listen)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8765
    state = HTTPProxyState(target_url, rules, record_path)
    server = ThreadingHTTPServer((host, port), make_handler(state))
    print(f"mcp-faultlab HTTP proxy listening on http://{host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.shutdown()
        server.server_close()
        state.close()
    return 0

