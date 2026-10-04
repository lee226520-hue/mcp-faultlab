#!/usr/bin/env python3
import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if method == "tools/list":
        response = {"id": request.get("id"), "result": {"tools": [{"name": "search", "description": "Search public documents"}]}}
    elif method == "tools/call":
        params = request.get("params") or {}
        response = {"id": request.get("id"), "result": {"ok": True, "tool": params.get("name"), "echo": params.get("arguments", {})}}
    else:
        response = {"id": request.get("id"), "error": {"code": -32601, "message": "method not found"}}
    print(json.dumps(response), flush=True)
