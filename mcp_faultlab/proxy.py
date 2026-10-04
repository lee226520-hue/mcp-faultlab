import json
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .runner import _fault_for, _injected_response
from .redaction import redact


def create_http_server(listen, upstream, faults):
    """Create a controllable HTTP proxy server and its in-memory event list."""
    host, port = listen.rsplit(":", 1)
    events = []

    class Handler(BaseHTTPRequestHandler):
        proxy_upstream = upstream
        proxy_faults = faults
        proxy_events = events

        def do_POST(self):
            started = time.time()
            size = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(size)
            try:
                request = json.loads(body.decode("utf-8"))
            except Exception:
                self.send_error(400, "expected JSON")
                return
            sequence = len([event for event in self.proxy_events if event.get("type") == "request"])
            request_event = {"type": "request", "transport": "http", "sequence": sequence, "time": started, "id": request.get("id", sequence + 1), "method": request.get("method"), "params": request.get("params", {})}
            self.proxy_events.append(request_event)
            fault = _fault_for(self.proxy_faults, request)
            injected, outcome = _injected_response(fault or {})
            if fault and fault.get("delay_ms"):
                time.sleep(min(float(fault["delay_ms"]) / 1000, 10))
            if injected is not None or outcome == "timeout":
                response = injected or {"error": {"code": "TIMEOUT", "message": "fault injected"}}
                response_kind = outcome
            else:
                try:
                    forward = urllib.request.Request(self.proxy_upstream, data=body, headers={"Content-Type": "application/json"}, method="POST")
                    with urllib.request.urlopen(forward, timeout=30) as upstream_response:
                        response = json.loads(upstream_response.read().decode("utf-8"))
                    response_kind = "target"
                except Exception as exc:
                    response = {"error": {"code": "UPSTREAM_ERROR", "message": str(exc)}}
                    response_kind = "error"
            response_event = {"type": "response", "transport": "http", "sequence": sequence, "time": time.time(), "id": request_event["id"], "response": response, "response_kind": response_kind, "status": "recoverable" if response_kind in ("timeout", "error") else "completed", "latency_ms": round((time.time() - started) * 1000, 2)}
            if fault:
                response_event["fault_kind"] = fault.get("kind")
                response_event["fault"] = {k: v for k, v in fault.items() if k != "result" or len(str(v)) < 500}
                if fault.get("security"):
                    response_event["attack_injected"] = True
            self.proxy_events.append(response_event)
            encoded = json.dumps(response, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_args):
            return

    return ThreadingHTTPServer((host, int(port)), Handler), events


def serve_http(listen, upstream, faults, cassette_path=None):
    server, events = create_http_server(listen, upstream, faults)
    try:
        host, port = server.server_address
        print("mcp-faultlab HTTP proxy listening on http://%s:%s -> %s" % (host, port, upstream), flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if cassette_path:
            with open(cassette_path, "w", encoding="utf-8") as handle:
                json.dump({"version": 2, "transport": "http", "upstream": upstream, "events": redact(events)}, handle, ensure_ascii=False, indent=2)
