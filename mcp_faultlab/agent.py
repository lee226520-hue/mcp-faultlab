"""Two-process agent-through-proxy execution mode.

The agent writes JSON-RPC-like tool requests to stdout. Faultlab applies faults,
optionally forwards the request to a tool server, and writes the response to the
agent's stdin. This keeps the runner independent from a particular Agent SDK
while exercising the actual agent decision loop.
"""

import json
import os
import subprocess
import time

from .attacks import printable_fault, resolve_fault
from .runner import _build_result, _injected_response, _matches, _readline_timeout
from .scenario import command_args


def _config(value):
    value = value or {}
    environment = None
    if value.get("env"):
        environment = os.environ.copy()
        environment.update({str(key): str(item) for key, item in value["env"].items()})
    return {
        "timeout_seconds": max(0.01, float(value.get("response_timeout_ms", 5000)) / 1000),
        "max_response_bytes": max(1024, int(value.get("max_response_bytes", 1024 * 1024))),
        "cwd": value.get("cwd"),
        "env": environment,
    }


def _spawn(config):
    return subprocess.Popen(command_args(config["command"]), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, cwd=config.get("cwd"), env=config.get("env"))


def run_agent_scenario(scenario):
    started = time.time()
    agent_spec = scenario["agent"]
    server_spec = scenario["server"]
    agent_config = _config(agent_spec)
    server_config = _config(server_spec)
    agent = _spawn({**agent_config, "command": agent_spec["command"]})
    server = _spawn({**server_config, "command": server_spec["command"]})
    events = []
    fault_counts = {}
    sequence = 0
    limit = int(scenario.get("max_steps", agent_spec.get("max_steps", 50)))
    limit_hit = False
    try:
        while sequence < limit:
            try:
                line = _readline_timeout(agent.stdout, agent_config["timeout_seconds"])
            except TimeoutError:
                events.append({"type": "response", "sequence": sequence, "time": time.time(), "id": None, "response": {"error": "agent response timed out"}, "response_kind": "timeout", "status": "recoverable"})
                break
            if not line:
                break
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                events.append({"type": "response", "sequence": sequence, "time": time.time(), "id": None, "response": {"error": "agent emitted invalid JSON"}, "response_kind": "error", "status": "recoverable"})
                break
            request = dict(request)
            request.setdefault("id", sequence + 1)
            fault = None
            fault_index = None
            for index, raw in enumerate(scenario.get("faults", [])):
                candidate = resolve_fault(raw)
                max_times = candidate.get("times", candidate.get("repeat", None))
                if max_times is not None and fault_counts.get(index, 0) >= int(max_times):
                    continue
                if _matches(candidate, request):
                    fault, fault_index = candidate, index
                    fault_counts[index] = fault_counts.get(index, 0) + 1
                    break
            request_event = {"type": "request", "transport": "agent-proxy", "sequence": sequence, "time": time.time(), "id": request["id"], "method": request.get("method"), "params": request.get("params", {})}
            events.append(request_event)
            injected, outcome = _injected_response(fault or {})
            if fault and fault.get("delay_ms"):
                time.sleep(min(float(fault["delay_ms"]) / 1000, 10))
            response, response_kind = injected, outcome
            if injected is None and outcome != "timeout":
                try:
                    server.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                    server.stdin.flush()
                    server_line = _readline_timeout(server.stdout, server_config["timeout_seconds"])
                except TimeoutError:
                    server_line = ""
                    response, response_kind = {"error": "server response timed out"}, "timeout"
                except (BrokenPipeError, OSError) as error:
                    server_line = ""
                    response, response_kind = {"error": "server write failed: %s" % error}, "error"
                if response is None:
                    if not server_line:
                        response, response_kind = {"error": "server exited without response"}, "error"
                    elif len(server_line.encode("utf-8")) > server_config["max_response_bytes"]:
                        response, response_kind = {"error": "server response too large"}, "error"
                    else:
                        try:
                            response, response_kind = json.loads(server_line), "target"
                        except json.JSONDecodeError:
                            response, response_kind = {"raw": server_line.rstrip()}, "error"
            response_event = {"type": "response", "transport": "agent-proxy", "sequence": sequence, "time": time.time(), "id": request["id"], "response": response, "response_kind": response_kind, "status": "recoverable" if response_kind in ("timeout", "error") else "completed"}
            if fault:
                response_event["fault_kind"] = fault.get("kind")
                response_event["fault"] = printable_fault(fault)
                response_event["fault_index"] = fault_index
                if fault.get("security"):
                    response_event["attack_injected"] = True
            events.append(response_event)
            try:
                agent.stdin.write(json.dumps(response, ensure_ascii=False) + "\n")
                agent.stdin.flush()
            except (BrokenPipeError, OSError):
                break
            sequence += 1
        else:
            limit_hit = True
    finally:
        for process in (agent, server):
            try:
                process.stdin.close()
            except Exception:
                pass
        for process in (agent, server):
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass
        stderr = "agent:\n%s\nserver:\n%s" % (agent.stderr.read()[-2000:], server.stderr.read()[-2000:])
        agent.stdout.close()
        agent.stderr.close()
        server.stdout.close()
        server.stderr.close()
    result = _build_result(scenario, events, started, stderr, agent_spec["command"], agent.returncode)
    result["transport"] = "agent-proxy"
    result["agent_returncode"] = agent.returncode
    result["server_returncode"] = server.returncode
    if limit_hit:
        result["status"] = "failed"
        result["passed"] = False
        result["limit_hit"] = limit
    return result
