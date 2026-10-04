# mcp-faultlab

Deterministic failure testing for MCP tools and AI agents.

Most Agent demos test the happy path. `mcp-faultlab` makes the dangerous path
repeatable: a tool times out, returns an error, serves stale data, or changes
its server error shape. You can record the real exchange once, run it offline,
and turn a failure into a CI regression case.

## The 30-second demo

```bash
python3 examples/run_demo.py
```

The demo starts a tiny MCP-like stdio server, injects an error into the first
`search` call, retries it, and records the exchange. The output shows the
failure and recovery rather than hiding either one.

## Install

```bash
python3 -m pip install -e .
```

The core package uses only the Python standard library.

## Put a server behind the proxy

```bash
python3 -m mcp_faultlab proxy \
  --target "python3 server.py" \
  --fault examples/fault.json \
  --record artifacts/run.json
```

The proxy correlates concurrent JSON-RPC responses by request ID, forwards
server notifications, and writes a versioned cassette. Cassettes are written
atomically and common secrets are redacted before they reach disk.

## Fault rules

```json
{
  "faults": [
    {"kind": "tool_error", "tool": "search", "occurrence": 1},
    {"kind": "stale_data", "tool": "search", "occurrence": 2, "replacement": "cached"}
  ]
}
```

Supported kinds:

- `tool_error`: return an MCP tool result with `isError: true`;
- `server_error`: return a JSON-RPC error response;
- `stale_data`: replace the tool content while keeping the call successful;
- `timeout`: delay the response by `delay_ms`;
- `drop`: suppress the response to exercise client timeout handling.

Rules can match `method`, `tool`, and `occurrence`. Use `"every": true` or
`"occurrence": "all"` to apply a rule to every matching call.

## Replay without the real server

```bash
python3 -m mcp_faultlab replay artifacts/run.json
```

Replay is local and deterministic: it does not contact the original server or
use its credentials. Response IDs are rewritten to match the current client.

## Generate a fault campaign

Turn one healthy recording into several deterministic failure fixtures:

```bash
python3 -m mcp_faultlab campaign artifacts/healthy.json \
  --faults examples/campaign.json \
  --out artifacts/cases
```

Each generated cassette can be served independently in a test job.

## Share a visual failure report

```bash
python3 -m mcp_faultlab report artifacts/run.json --out artifacts/report.html
```

The report is a single offline HTML file with summary cards, searchable event
timeline, fault badges, and before/delivered payloads. It can be attached to a
CI artifact or opened locally without a backend.

## Proxy an HTTP MCP endpoint

For JSON MCP requests over Streamable HTTP:

```bash
python3 -m mcp_faultlab http-proxy \
  --listen 127.0.0.1:8765 \
  --target-url http://127.0.0.1:9000/mcp \
  --fault examples/fault.json \
  --record artifacts/http-run.json
```

JSON responses are recorded and can be faulted with the same rule format.
Event-stream responses are forwarded transparently and recorded as metadata;
the fully deterministic replay path remains the stdio transport for now.

## Verify in CI

```bash
python3 -m mcp_faultlab verify \
  fixtures/expected.json \
  artifacts/actual.json
```

The verifier ignores timestamps, request IDs, and cassette metadata by
default, and returns a non-zero exit code with the first useful JSON path when
behavior diverges.

It is also available as a reusable composite action from this repository:

```yaml
- uses: your-org/mcp-faultlab@main
  with:
    expected: fixtures/expected.json
    actual: artifacts/actual.json
```

## Design boundaries

Version 0.2 focuses on MCP stdio plus a JSON Streamable HTTP proxy. The stdio
proxy supports concurrent in-flight requests, but the replay server follows the
request order in the cassette. Richer structural matching and a native GitHub
Action are the next extension points.

This is a testing tool, not a security boundary. It can execute the target
command you provide, and automatic redaction is best-effort. Inspect cassettes
before sharing them.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 examples/run_demo.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## License

MIT
