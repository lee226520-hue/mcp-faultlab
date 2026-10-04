"""Concurrent, request-correlating MCP stdio proxy."""

from __future__ import annotations

import shlex
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Any, TextIO

from .cassette import add_event, new_cassette, save
from .faults import DropResponse, FaultEngine, FaultRule
from .protocol import decode, encode, has_id, id_key, is_request, is_response, message_id


@dataclass
class Pending:
    message: dict[str, Any]
    request_sequence: int
    rules: list[FaultRule]


def _send(stream: TextIO, message: dict[str, Any], lock: threading.Lock) -> None:
    with lock:
        stream.write(encode(message) + "\n")
        stream.flush()


def run_proxy(
    target: str,
    rules: list[FaultRule] | None = None,
    record_path: str | None = None,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
) -> int:
    command = shlex.split(target)
    if not command:
        raise ValueError("target command is empty")
    child = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=1,
    )
    assert child.stdin is not None and child.stdout is not None

    cassette = (
        new_cassette(target, metadata={"transport": "stdio", "redaction": "automatic"})
        if record_path
        else None
    )
    engine = FaultEngine(rules)
    pending: dict[str, Pending] = {}
    pending_lock = threading.Lock()
    output_lock = threading.Lock()
    cassette_lock = threading.Lock()
    stop = threading.Event()
    sequence = 0
    sequence_lock = threading.Lock()
    delivery_threads: list[threading.Thread] = []
    delivery_lock = threading.Lock()

    def next_sequence() -> int:
        nonlocal sequence
        with sequence_lock:
            sequence += 1
            return sequence

    def record(direction: str, message: dict[str, Any], **extra: Any) -> None:
        if cassette is None:
            return
        with cassette_lock:
            add_event(
                cassette,
                direction,
                message,
                sequence=next_sequence(),
                request_id=message_id(message) if has_id(message) else None,
                **extra,
            )

    def target_reader() -> None:
        def deliver(response: dict[str, Any], context: Pending | None) -> None:
            delivered = response
            fault_kind: str | None = None
            if context and context.rules:
                for rule in context.rules:
                    fault_kind = rule.kind
                    try:
                        delivered = rule.mutate(delivered)
                    except DropResponse:
                        delivered = None
                        break

            if delivered is not None:
                extra: dict[str, Any] = {}
                if context:
                    extra["request_sequence"] = context.request_sequence
                if fault_kind:
                    extra["fault"] = fault_kind
                    extra["message_before_fault"] = response
                record("server->client", delivered, **extra)
                _send(stdout, delivered, output_lock)
            elif context:
                record(
                    "server->client",
                    {"dropped": True, "request_id": message_id(response)},
                    request_sequence=context.request_sequence,
                    fault=fault_kind or "drop",
                    message_before_fault=response,
                )

        try:
            for raw in child.stdout:
                if stop.is_set():
                    break
                try:
                    response = decode(raw)
                except Exception as exc:
                    print(f"mcp-faultlab: invalid target message: {exc}", file=sys.stderr)
                    continue
                if response is None:
                    continue

                key = id_key(message_id(response)) if is_response(response) else None
                with pending_lock:
                    context = pending.pop(key, None) if key is not None else None
                delivery = threading.Thread(
                    target=deliver,
                    args=(response, context),
                    name="mcp-faultlab-delivery",
                    daemon=True,
                )
                with delivery_lock:
                    delivery_threads.append(delivery)
                delivery.start()
        finally:
            with delivery_lock:
                active = list(delivery_threads)
            for delivery in active:
                delivery.join(timeout=3)
            stop.set()

    reader = threading.Thread(target=target_reader, name="mcp-faultlab-target-reader", daemon=True)
    reader.start()

    try:
        for raw in stdin:
            if stop.is_set():
                break
            message = decode(raw)
            if message is None:
                continue
            request_sequence = next_sequence()
            record("client->server", message, request_sequence=request_sequence)

            if is_request(message) and has_id(message):
                selected = engine.observe(message)
                with pending_lock:
                    pending[id_key(message_id(message))] = Pending(message, request_sequence, selected)

            child.stdin.write(encode(message) + "\n")
            child.stdin.flush()
    finally:
        try:
            child.stdin.close()
        except Exception:
            pass
        if child.poll() is None:
            try:
                # A normal MCP server exits after its stdin reaches EOF. Give
                # the reader time to forward all in-flight responses before
                # using termination as the fallback.
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.terminate()
                try:
                    child.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    child.kill()
        reader.join(timeout=2)
        stop.set()
        try:
            child.stdout.close()
        except Exception:
            pass
        if cassette is not None and record_path:
            save(record_path, cassette)
    return 0
