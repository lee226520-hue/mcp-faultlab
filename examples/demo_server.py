"""Tiny MCP-like stdio server used by the end-to-end demo."""

import json
import sys


def send(value):
    sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if "id" not in request:
        continue
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": request["id"], "result": {"protocolVersion": "2025-11-25"}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": request["id"], "result": {"tools": [{"name": "search"}]}})
    elif method == "tools/call":
        send({
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {"isError": False, "content": [{"type": "text", "text": "fresh result"}]},
        })
    else:
        send({"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32601, "message": "not found"}})

