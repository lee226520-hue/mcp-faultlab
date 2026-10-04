"""Tiny out-of-order JSON-RPC server used to exercise proxy correlation."""

import json
import sys
import threading
import time


def respond(request):
    # Request 1 deliberately completes after request 2.
    if request.get("id") == 1:
        time.sleep(0.08)
    message = {"jsonrpc": "2.0", "id": request.get("id"), "result": {"id": request.get("id")}}
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


threads = []
for line in sys.stdin:
    request = json.loads(line)
    thread = threading.Thread(target=respond, args=(request,), daemon=True)
    thread.start()
    threads.append(thread)
for thread in threads:
    thread.join()

