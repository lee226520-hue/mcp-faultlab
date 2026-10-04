import argparse
import json
import os
import sys

from . import __version__
from .attacks import PACKS
from .campaign import run_campaign
from .proxy import serve_http
from .report import output_paths, write_html, write_json
from .replay import serve as serve_replay
from .runner import run_scenario
from .scenario import load_scenario, validate_scenario


TEMPLATE = '''name: agent-safety
target:
  command: python3 examples/demo_server.py
requests:
  - id: 1
    method: tools/call
    params:
      name: search
      arguments: {q: faultlab}
faults:
  - kind: timeout
    method: tools/call
    delay_ms: 8000
assertions:
  - no_duplicate_tool_call
  - final_status: recoverable
  - max_retries: 2
'''


def _main(argv=None):
    parser = argparse.ArgumentParser(prog="mcp-faultlab", description="Break your agent before production")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("directory")
    sub.add_parser("packs")
    validate = sub.add_parser("validate")
    validate.add_argument("scenario")
    run = sub.add_parser("run")
    run.add_argument("scenario")
    run.add_argument("--out", default=None)
    replay = sub.add_parser("replay")
    replay.add_argument("cassette")
    replay.add_argument("--json", action="store_true", help="print recorded responses as JSONL")
    replay.add_argument("--serve", action="store_true", help="serve recorded responses over JSONL stdin/stdout")
    replay.add_argument("--lenient", action="store_true", help="match by id without checking method and params")
    proxy = sub.add_parser("proxy")
    proxy.add_argument("scenario")
    proxy.add_argument("--listen", default="127.0.0.1:8787")
    proxy.add_argument("--upstream", required=True)
    proxy.add_argument("--cassette", default=None)
    report = sub.add_parser("report")
    report.add_argument("run_json")
    args = parser.parse_args(argv)
    if args.command == "init":
        os.makedirs(args.directory, exist_ok=True)
        path = os.path.join(args.directory, "agent-safety.yml")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(TEMPLATE)
        print(path)
        return 0
    if args.command == "packs":
        for name in PACKS:
            print(name)
        return 0
    if args.command == "validate":
        scenario = load_scenario(args.scenario, require_target=False)
        has_target = bool((scenario.get("target") or {}).get("command"))
        proxy_scenario = scenario.get("transport") == "http"
        errors = validate_scenario(scenario, require_target=has_target or not proxy_scenario, require_requests=has_target or not proxy_scenario)
        if errors:
            for error in errors:
                print("ERROR", error)
            return 1
        print("valid:", args.scenario)
        return 0
    if args.command == "run":
        if os.path.isdir(args.scenario):
            output_dir = args.out or "faultlab-report"
            summary = run_campaign(args.scenario, output_dir)
            print("%d passed · %d failed · %d security violation · %d attack injected" % (summary["passed_count"], summary["failed_count"], summary["security_violations"], summary["attack_injections"]))
            print("report:", summary["html_path"])
            summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary_path:
                with open(summary_path, "a", encoding="utf-8") as github_summary:
                    github_summary.write("## mcp-faultlab campaign\n\n%d passed · %d failed · %d security violation · %d attack injected\n\n" % (summary["passed_count"], summary["failed_count"], summary["security_violations"], summary["attack_injections"]))
                    github_summary.write("| Scenario | Result | Assertions failed | Security violations |\n|---|---|---:|---:|\n")
                    for item in summary["scenarios"]:
                        github_summary.write("| %s | %s | %s | %s |\n" % (item.get("scenario"), "PASS" if item.get("passed") else "FAIL", item.get("assertions_failed", 0), item.get("security_violations", 0)))
            return 0 if summary["passed"] else 1
        scenario = load_scenario(args.scenario)
        errors = validate_scenario(scenario)
        if errors:
            for error in errors:
                print("ERROR", error)
            return 1
        result = run_scenario(scenario)
        run_path, html_path, cassette_path = output_paths(args.scenario, args.out)
        os.makedirs(os.path.dirname(run_path), exist_ok=True)
        write_json(run_path, result)
        write_html(html_path, result)
        write_json(cassette_path, {"version": 2, "transport": result.get("transport", "stdio"), "scenario": result["scenario"], "command": result["command"], "metrics": result.get("metrics", {}), "events": result["events"]})
        passed = sum(1 for item in result["assertions"] if item["passed"])
        failed = len(result["assertions"]) - passed
        print("%d passed · %d failed · %d security violation · %d attack injected" % (passed, failed, result["security_violations"], result.get("attack_injections", 0)))
        print("report:", html_path)
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as summary:
                summary.write("## mcp-faultlab: %s\n\n%d passed · %d failed · %d security violation · %d attack injected\n\n" % (result["scenario"], passed, failed, result["security_violations"], result.get("attack_injections", 0)))
                summary.write("| Assertion | Result | Evidence |\n|---|---|---|\n")
                for item in result["assertions"]:
                    summary.write("| %s | %s | %s |\n" % (item["name"], "PASS" if item["passed"] else "FAIL", item["detail"]))
        return 0 if result["passed"] else 1
    if args.command == "replay":
        with open(args.cassette, "r", encoding="utf-8") as handle:
            cassette = json.load(handle)
        if args.serve:
            serve_replay(cassette, strict=not args.lenient)
            return 0
        if not args.json:
            print("Replay: %s (%d events)" % (cassette.get("scenario", "unknown"), len(cassette.get("events", []))))
        for event in cassette.get("events", []):
            if event.get("type") == "response":
                if args.json:
                    print(json.dumps({"id": event.get("id"), "response": event.get("response"), "status": event.get("status")}, ensure_ascii=False))
                else:
                    print("  id=%s %s" % (event.get("id"), event.get("response_kind", "response")))
        return 0
    if args.command == "proxy":
        scenario = load_scenario(args.scenario, require_target=False)
        errors = validate_scenario(scenario, require_target=False, require_requests=False)
        if errors:
            for error in errors:
                print("ERROR", error)
            return 1
        serve_http(args.listen, args.upstream, scenario.get("faults", []), args.cassette)
        return 0
    if args.command == "report":
        with open(args.run_json, "r", encoding="utf-8") as handle:
            result = json.load(handle)
        html_path = os.path.splitext(args.run_json)[0] + ".html"
        if "scenarios" in result:
            from .report import write_campaign_html
            write_campaign_html(html_path, result)
        else:
            write_html(html_path, result)
        print(html_path)
        return 0
    return 2


def main(argv=None):
    try:
        return _main(argv)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("error:", error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
