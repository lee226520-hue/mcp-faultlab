import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    print(json.dumps({"id": request.get("id"), "result": {"content": "X" * 5000}}), flush=True)
