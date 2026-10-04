# Security policy

## Scope

`mcp-faultlab` is a local testing proxy. It can observe and forward arbitrary
MCP traffic and can start a target subprocess. Treat target commands,
cassettes, and fault configurations as trusted developer-controlled input.

## Reporting

Please do not publish credentials or exploitable details in an issue. Report a
security problem privately to the repository maintainers with reproduction
steps, affected versions, and a minimal fixture.

## Safe defaults

- Cassettes automatically redact common token fields and well-known token formats.
- Replay never contacts the original server.
- Fault injection is local and does not need model or service credentials.
- Redaction is best-effort; inspect a cassette before sharing it.

