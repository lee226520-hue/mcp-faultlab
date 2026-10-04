# Changelog

## Unreleased

- add searchable, self-contained HTML failure reports;
- add a JSON Streamable HTTP proxy with transparent event-stream forwarding;
- add HTTP integration coverage where local socket binding is available.
- add ten built-in attack packs and `mcp-faultlab packs` discovery;
- allow attack packs in the same JSON fault configuration as transport faults.

## 0.2.0

- correlate concurrent MCP stdio responses by JSON-RPC request ID;
- add fault rules for tool errors, server errors, stale data, timeouts, and drops;
- add deterministic replay, campaign generation, and cassette verification;
- redact common secrets before persistence;
- add Docker packaging, schemas, CI workflow, tests, and design/security docs.

## 0.1.0

- initial sequential proxy, replay server, and demo.
