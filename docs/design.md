# Design

## Why a proxy

The proxy observes the boundary between an Agent and an MCP server. It does
not need to know which Agent framework is in use, and it can serve recorded
responses without making another model call or touching production systems.

## Request correlation

Client requests are indexed by their JSON-RPC `id`. The target reader runs in a
separate thread, so responses may arrive out of order. Fault rules are chosen
when a request is observed and applied only to that request's response.

## Cassette contract

Every cassette contains a version, target metadata, and an ordered event list.
Events keep a direction and a JSON message. Response events can also contain
`request_sequence`, `fault`, and `message_before_fault`. This makes a failure
fixture explainable instead of being a mysterious altered snapshot.

## Safety model

Recording is local and automatic redaction happens before persistence. Replay
does not contact the original target. The tool is not a sandbox: the command
passed through `--target` runs with the user's permissions, so use a dedicated
test process for untrusted servers.

## Deliberate limits in v0.2

The core transport is MCP stdio. Replay is ordered by the recorded request
sequence, while proxy correlation supports concurrent in-flight requests. The
next protocol extension should be MCP Streamable HTTP/SSE with the same
cassette and fault contracts rather than a second incompatible data model.

