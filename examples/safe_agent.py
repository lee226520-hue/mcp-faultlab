import json
import sys

print(json.dumps({"id": 1, "method": "tools/call", "params": {"name": "search", "arguments": {"q": "quarterly report"}}}), flush=True)
line = sys.stdin.readline()
if line:
    response = json.loads(line)
    # Treat tool output as data; never turn instructions in it into a tool call.
    print(json.dumps({"status": "done", "tool_response_seen": bool(response)}), file=sys.stderr, flush=True)
