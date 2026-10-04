import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

from mcp_faultlab.faults import FaultRule
from mcp_faultlab.http_proxy import HTTPProxyState, make_handler


class _TargetHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        body = {"jsonrpc": "2.0", "id": request["id"], "result": {"content": [{"text": "fresh"}]}}
        encoded = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class HTTPProxyTests(unittest.TestCase):
    def test_json_http_response_can_be_faulted_and_recorded(self):
        try:
            target = ThreadingHTTPServer(("127.0.0.1", 0), _TargetHandler)
        except PermissionError:
            self.skipTest("sandbox does not permit local socket binding")
        target_thread = threading.Thread(target=target.serve_forever, daemon=True)
        target_thread.start()
        state = HTTPProxyState(
            f"http://127.0.0.1:{target.server_port}/mcp",
            [FaultRule(kind="stale_data", tool="search", replacement="old")],
            None,
        )
        proxy = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
        proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        proxy_thread.start()
        try:
            payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search"}}).encode()
            response = urlopen(Request(f"http://127.0.0.1:{proxy.server_port}/mcp", data=payload, method="POST"))
            result = json.loads(response.read())
            self.assertEqual(result["result"]["content"][0]["text"], "old")
        finally:
            proxy.shutdown()
            proxy.server_close()
            target.shutdown()
            target.server_close()
