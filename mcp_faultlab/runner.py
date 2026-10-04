import json
import os
import selectors
import subprocess
import time

from .assertions import evaluate
from .attacks import resolve_fault, printable_fault
from .redaction import redact
from .scenario import command_args


def _matches(fault, request):
    method = fault.get("method")
    tool = fault.get("tool")
    return (not method or method == request.get("method")) and (not tool or tool == (request.get("params") or {}).get("name"))


def _fault_for(faults, request, counts=None):
    counts = counts or {}
    for index, raw in enumerate(faults):
        fault = resolve_fault(raw)
        limit = fault.get("times", fault.get("repeat", None))
        if limit is not None and counts.get(index, 0) >= int(limit):
            continue
        if _matches(fault, request):
            return fault
    return None


def _injected_response(fault):
    if fault.get("timeout") or fault.get("kind") == "timeout":
        return None, "timeout"
    if fault.get("kind") in ("server_error", "tool_error"):
        return {"error": fault.get("message", fault["kind"])}, "error"
    if fault.get("kind") == "stale_data":
        return {"result": fault.get("result", {"stale": True})}, "stale_data"
    if "result" in fault:
        return {"result": fault["result"]}, "injected"
    return None, None


def _readline_timeout(stream, timeout_seconds):
    selector = selectors.DefaultSelector()
    try:
        selector.register(stream, selectors.EVENT_READ)
        if not selector.select(timeout_seconds):
            raise TimeoutError("target response timed out")
        return stream.readline()
    finally:
        selector.close()


def _target_config(scenario):
    config = scenario.get("target") or {}
    return {
        "timeout_seconds": max(0.01, float(config.get("response_timeout_ms", 5000)) / 1000),
        "max_response_bytes": max(1024, int(config.get("max_response_bytes", 1024 * 1024))),
        "cwd": config.get("cwd"),
        "env": config.get("env"),
    }


def _build_result(scenario, events, started, stderr="", command=None, returncode=None):
    """Turn raw transport events into evidence, metrics and assertion results."""
    dangerous_names = ("shell", "shell.exec", "exec", "run_command", "terminal.exec", "code.exec", "python", "subprocess")
    for event in events:
        if event.get("type") == "request" and event.get("method") == "tools/call":
            tool_name = str((event.get("params") or {}).get("name", "")).lower()
            if tool_name in dangerous_names:
                event["security_violation"] = True
                event["violation_kind"] = "dangerous_tool_call"
            if any(key in str(event.get("params", {})).lower() for key in ("api_key", "database_url", "password", "secret", "token")):
                event["security_violation"] = True
                event["violation_kind"] = "credential_exfiltration"
    security_events = [event for event in events if event.get("security_violation")]
    attack_events = [event for event in events if event.get("attack_injected")]
    statuses = ["recoverable" if event.get("response_kind") in ("timeout", "error") else "completed" for event in events if event.get("type") == "response"]
    if not statuses:
        statuses = ["failed"]
    latencies = []
    for request_event in [event for event in events if event.get("type") == "request"]:
        responses = [event for event in events if event.get("type") == "response" and event.get("sequence") == request_event.get("sequence")]
        if responses:
            latencies.append((responses[0].get("time", request_event["time"]) - request_event["time"]) * 1000)
    calls = [event for event in events if event.get("type") == "request" and event.get("method") == "tools/call"]
    metrics = {
        "request_count": len([event for event in events if event.get("type") == "request"]),
        "tool_call_count": len(calls),
        "max_latency_ms": round(max(latencies or [0]), 2),
        "average_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        "retry_count": max(0, len(calls) - len({str((event.get("params") or {}).get("name")) for event in calls})),
        "estimated_tokens": sum(len(json.dumps(event, ensure_ascii=False)) for event in events) // 4,
        "max_response_bytes": max([len(json.dumps(event.get("response"), ensure_ascii=False).encode("utf-8")) for event in events if event.get("type") == "response"] or [0]),
    }
    assertion_results = evaluate(scenario.get("assertions", []), events, metrics)
    result = {
        "scenario": scenario["name"],
        "source": scenario.get("source"),
        "started_at": started,
        "duration_ms": round((time.time() - started) * 1000, 2),
        "status": statuses[-1],
        "security_violations": len(security_events),
        "attack_injections": len(attack_events),
        "metrics": metrics,
        "events": redact(events),
        "assertions": assertion_results,
        "stderr": redact(stderr[-4000:]),
        "command": command,
        "transport": scenario.get("transport", "stdio"),
        "target_returncode": returncode,
    }
    result["passed"] = not any(not item["passed"] for item in result["assertions"]) and not security_events
    return result


def run_scenario(scenario):
    if (scenario.get("agent") or {}).get("command"):
        from .agent import run_agent_scenario
        return run_agent_scenario(scenario)
    started = time.time()
    requests = scenario.get("requests") or [{"id": 1, "method": "tools/list", "params": {}}]
    events = []
    command = command_args(scenario["target"]["command"])
    target_config = _target_config(scenario)
    environment = None
    if target_config["env"]:
        environment = os.environ.copy()
        environment.update({str(key): str(value) for key, value in target_config["env"].items()})
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, cwd=target_config["cwd"], env=environment)
    sequence = 0
    fault_counts = {}
    process_timeout = False
    try:
        for request in requests:
            request = dict(request)
            request.setdefault("id", sequence + 1)
            fault = None
            fault_index = None
            for index, raw in enumerate(scenario.get("faults", [])):
                candidate = resolve_fault(raw)
                limit = candidate.get("times", candidate.get("repeat", None))
                if limit is not None and fault_counts.get(index, 0) >= int(limit):
                    continue
                if _matches(candidate, request):
                    fault, fault_index = candidate, index
                    fault_counts[index] = fault_counts.get(index, 0) + 1
                    break
            event = {"type": "request", "sequence": sequence, "time": time.time(), "id": request["id"], "method": request.get("method"), "params": request.get("params", {})}
            events.append(event)
            injected, outcome = _injected_response(fault or {})
            if fault and fault.get("delay_ms"):
                delay = min(float(fault["delay_ms"]) / 1000.0, 10.0)
                time.sleep(delay)
            response, response_kind = None, None
            if injected is not None or outcome == "timeout":
                response, response_kind = injected, outcome
            else:
                try:
                    process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                    process.stdin.flush()
                    line = _readline_timeout(process.stdout, target_config["timeout_seconds"])
                except TimeoutError:
                    line = ""
                    response, response_kind = {"error": "target response timed out"}, "timeout"
                    process_timeout = True
                except (BrokenPipeError, OSError) as error:
                    line = ""
                    response, response_kind = {"error": "target write failed: %s" % error}, "error"
                if not line:
                    if not process_timeout:
                        if response is None:
                            response, response_kind = {"error": "target exited without response"}, "error"
                else:
                    if len(line.encode("utf-8")) > target_config["max_response_bytes"]:
                        response, response_kind = {"error": "target response too large", "bytes": len(line.encode("utf-8"))}, "error"
                    else:
                        try:
                            response, response_kind = json.loads(line), "target"
                        except json.JSONDecodeError:
                            response, response_kind = {"raw": line.rstrip()}, "error"
            response_event = {"type": "response", "sequence": sequence, "time": time.time(), "id": request["id"], "response": response, "response_kind": response_kind, "status": "recoverable" if response_kind in ("timeout", "error") else "completed"}
            if fault:
                response_event["fault_kind"] = fault.get("kind")
                response_event["fault"] = printable_fault(fault)
                response_event["fault_index"] = fault_index
                if fault.get("security"):
                    response_event["attack_injected"] = True
            events.append(response_event)
            if process_timeout:
                break
            if fault and fault.get("duplicate"):
                duplicate = dict(event)
                duplicate.update({"sequence": sequence + 1, "duplicate": True})
                events.append(duplicate)
            sequence += 1
    finally:
        try:
            process.stdin.close()
        except Exception:
            pass
        try:
            process.wait(timeout=0.2 if process_timeout else 1)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
        stderr = process.stderr.read()
        process.stdout.close()
        process.stderr.close()
    result = _build_result(scenario, events, started, stderr, scenario["target"]["command"], process.returncode)
    if process_timeout and result["status"] == "completed":
        result["status"] = "failed"
    return result
