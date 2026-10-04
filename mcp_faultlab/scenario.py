import os
import shlex

from .yamlite import load


PACK_NAMES = {
    "tool_description_prompt_injection",
    "tool_result_prompt_injection",
    "env_exfiltration_request",
    "schema_drift",
    "fake_success",
    "duplicate_side_effect",
    "infinite_retry",
    "sensitive_result",
    "oversized_result",
    "dangerous_tool_chain",
    "stale_data",
}

KNOWN_FAULTS = PACK_NAMES | {"timeout", "delay", "server_error", "tool_error", "stale_data"}


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def load_scenario(path, require_target=True):
    raw = load(path) or {}
    if not isinstance(raw, dict):
        raise ValueError("scenario root must be a mapping")
    target = raw.get("target") or {}
    if isinstance(target, str):
        target = {"command": target}
    command = target.get("command") or raw.get("command")
    agent = raw.get("agent") or {}
    if isinstance(agent, str):
        agent = {"command": agent}
    server = raw.get("server") or {}
    if isinstance(server, str):
        server = {"command": server}
    if require_target and not command and not agent.get("command"):
        raise ValueError("scenario requires target.command")
    faults = list(_as_list(raw.get("faults")))
    for pack in _as_list(raw.get("attacks")):
        name = pack.get("name") if isinstance(pack, dict) else str(pack)
        if name not in PACK_NAMES:
            raise ValueError("unknown attack pack: %s" % name)
        fault = {"kind": name, "security": True}
        if isinstance(pack, dict):
            fault.update(pack)
        faults.append(fault)
    return {
        "name": raw.get("name") or os.path.splitext(os.path.basename(path))[0],
        "target": {"command": command, **{k: v for k, v in target.items() if k != "command"}},
        "agent": {"command": agent.get("command"), **{k: v for k, v in agent.items() if k != "command"}},
        "server": {"command": server.get("command"), **{k: v for k, v in server.items() if k != "command"}},
        "requests": _as_list(raw.get("requests")),
        "faults": faults,
        "assertions": _as_list(raw.get("assertions")),
        "transport": raw.get("transport", "stdio"),
        "source": os.path.abspath(path),
    }


def command_args(command):
    return shlex.split(command) if isinstance(command, str) else list(command)


KNOWN_ASSERTIONS = {
    "no_duplicate_tool_call", "no_duplicate_side_effect", "final_status", "max_retries", "max_latency_ms",
    "max_tool_calls", "no_sensitive_data_exfiltration", "no_api_key_to_tool",
    "no_sensitive_data_in_results", "no_dangerous_tool_call", "no_shell_execution", "max_result_bytes",
    "no_tool_after_timeout", "no_schema_drift_execution", "replay_consistent", "no_stale_data_used",
    "no_security_violation",
}


def validate_scenario(scenario, require_target=True, require_requests=True):
    errors = []
    if not scenario.get("name"):
        errors.append("name is required")
    agent_mode = bool((scenario.get("agent") or {}).get("command"))
    if require_target and not (scenario.get("target") or {}).get("command") and not agent_mode:
        errors.append("target.command is required")
    if agent_mode and not (scenario.get("server") or {}).get("command"):
        errors.append("server.command is required in agent mode")
    if require_requests and not agent_mode and (not isinstance(scenario.get("requests"), list) or not scenario.get("requests")):
        errors.append("requests must be a non-empty list")
    for index, request in enumerate(scenario.get("requests", [])):
        if not isinstance(request, dict):
            errors.append("requests[%d] must be a mapping" % index)
        elif not request.get("method"):
            errors.append("requests[%d].method is required" % index)
    for index, fault in enumerate(scenario.get("faults", [])):
        if not isinstance(fault, dict) or not fault.get("kind"):
            errors.append("faults[%d] must have kind" % index)
        elif fault.get("kind") not in KNOWN_FAULTS:
            errors.append("faults[%d] unknown: %s" % (index, fault.get("kind")))
    for index, assertion in enumerate(scenario.get("assertions", [])):
        name = assertion if isinstance(assertion, str) else next(iter(assertion), None) if isinstance(assertion, dict) else None
        if name not in KNOWN_ASSERTIONS:
            errors.append("assertions[%d] unknown: %s" % (index, name))
    return errors
