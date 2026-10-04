"""Run the end-to-end fault injection demo."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def request(proc, value):
    proc.stdin.write(json.dumps(value) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


def run(cassette: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "mcp_faultlab",
        "proxy",
        "--target",
        f"{sys.executable} {ROOT / 'examples' / 'demo_server.py'}",
        "--fault",
        str(ROOT / "examples" / "fault.json"),
        "--record",
        str(cassette),
    ]
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        print("initialize:", request(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize"}))
        print("tools/list:", request(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
        first = request(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "search"}})
        print("first tool call (fault injected):", first)
        if first.get("result", {}).get("isError"):
            second = request(proc, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "search"}})
            print("retry:", second)
    finally:
        proc.stdin.close()
        proc.wait(timeout=3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="keep the cassette at this path")
    args = parser.parse_args()
    if args.out:
        cassette = Path(args.out)
        run(cassette)
        print(f"cassette written to: {cassette}")
        return 0
    with tempfile.TemporaryDirectory() as directory:
        cassette = Path(directory) / "run.json"
        run(cassette)
        print(f"cassette written to: {cassette}")
        print(cassette.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

