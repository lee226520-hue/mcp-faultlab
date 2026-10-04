from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .campaign import write_campaign
from .cassette import load, summary
from .faults import parse_rules
from .http_proxy import serve_http
from .proxy import run_proxy
from .replay import serve
from .report import write_report
from .verify import compare_paths


def _json_file(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-faultlab",
        description="Record, replay, and chaos-test MCP stdio interactions.",
    )
    parser.add_argument("--version", action="version", version=f"mcp-faultlab {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    proxy = commands.add_parser("proxy", help="proxy an MCP stdio server")
    proxy.add_argument("--target", required=True, help="target command, quoted")
    proxy.add_argument("--fault", help="JSON fault rule or fault list")
    proxy.add_argument("--record", help="write a cassette JSON file")

    http_proxy = commands.add_parser("http-proxy", help="proxy an MCP Streamable HTTP endpoint")
    http_proxy.add_argument("--listen", default="127.0.0.1:8765", help="local host:port")
    http_proxy.add_argument("--target-url", required=True, help="upstream MCP HTTP URL")
    http_proxy.add_argument("--fault", help="JSON fault rule or fault list")
    http_proxy.add_argument("--record", help="write a cassette JSON file")

    replay = commands.add_parser("replay", help="serve a cassette as an MCP stdio server")
    replay.add_argument("cassette")

    inspect = commands.add_parser("inspect", help="summarize a cassette")
    inspect.add_argument("cassette")

    verify = commands.add_parser("verify", help="compare two cassettes for CI")
    verify.add_argument("expected")
    verify.add_argument("actual")
    verify.add_argument("--ignore-key", action="append", default=[], help="JSON key to ignore")

    campaign = commands.add_parser("campaign", help="generate faulted cassette variants")
    campaign.add_argument("cassette")
    campaign.add_argument("--faults", required=True, help="JSON fault list or named cases")
    campaign.add_argument("--out", required=True, help="output directory")

    report = commands.add_parser("report", help="write a self-contained HTML report")
    report.add_argument("cassette")
    report.add_argument("--out", required=True, help="HTML output path")
    report.add_argument("--title", help="report title")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "proxy":
            rules = parse_rules(_json_file(args.fault)) if args.fault else []
            return run_proxy(args.target, rules, args.record)
        if args.command == "http-proxy":
            rules = parse_rules(_json_file(args.fault)) if args.fault else []
            return serve_http(args.listen, args.target_url, rules, args.record)
        if args.command == "replay":
            return serve(args.cassette)
        if args.command == "inspect":
            print(summary(load(args.cassette)))
            return 0
        if args.command == "verify":
            ok, message = compare_paths(args.expected, args.actual, set(args.ignore_key))
            print(message)
            return 0 if ok else 1
        if args.command == "campaign":
            paths = write_campaign(args.cassette, _json_file(args.faults), args.out)
            for path in paths:
                print(path)
            return 0
        if args.command == "report":
            print(write_report(args.cassette, args.out, args.title))
            return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"mcp-faultlab: {exc}", file=sys.stderr)
        return 2
    return 2
