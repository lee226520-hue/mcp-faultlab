import json
import sys
from collections import defaultdict, deque


def _responses(cassette):
    return [event for event in cassette.get("events", []) if event.get("type") == "response"]


def _requests(cassette):
    return [event for event in cassette.get("events", []) if event.get("type") == "request"]


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def serve(cassette, input_stream=None, output_stream=None, strict=True):
    """Serve recorded responses over JSONL, for deterministic agent replay."""
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    responses = _responses(cassette)
    requests = _requests(cassette)
    by_id = defaultdict(deque)
    for event in responses:
        by_id[str(event.get("id"))].append(event)
    request_by_id = defaultdict(deque)
    for event in requests:
        request_by_id[str(event.get("id"))].append(event)
    cursor = 0
    for line in input_stream:
        if not line.strip():
            continue
        request = json.loads(line)
        request_id = str(request.get("id"))
        recorded_request = request_by_id[request_id].popleft() if request_by_id[request_id] else None
        event = by_id[request_id].popleft() if by_id[request_id] else None
        if not strict and event is None and cursor < len(responses):
            event = responses[cursor]
        if not strict and recorded_request is None and cursor < len(requests):
            recorded_request = requests[cursor]
        cursor += 1
        mismatch = False
        if strict and recorded_request:
            expected = {"method": recorded_request.get("method"), "params": recorded_request.get("params", {})}
            actual = {"method": request.get("method"), "params": request.get("params", {})}
            mismatch = _canonical(expected) != _canonical(actual)
        if mismatch:
            output = {"id": request.get("id"), "error": {"code": "REPLAY_MISMATCH", "message": "request differs from cassette", "expected": {"method": recorded_request.get("method"), "params": recorded_request.get("params", {})}}}
        elif event is None:
            output = {"id": request.get("id"), "error": {"code": "REPLAY_MISS", "message": "no recorded response"}}
        elif event.get("response_kind") == "timeout":
            output = {"id": request.get("id"), "error": {"code": "TIMEOUT", "message": "recorded timeout"}}
        else:
            output = event.get("response") or {"id": request.get("id"), "result": None}
            if isinstance(output, dict):
                output = dict(output)
                output["id"] = request.get("id", output.get("id"))
        output_stream.write(json.dumps(output, ensure_ascii=False) + "\n")
        output_stream.flush()
