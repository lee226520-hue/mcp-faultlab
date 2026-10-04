import json
import tempfile
import unittest
from pathlib import Path

from mcp_faultlab.campaign import apply_rules
from mcp_faultlab.cassette import add_event, new_cassette
from mcp_faultlab.faults import FaultEngine, FaultRule, parse_rules
from mcp_faultlab.redaction import redact
from mcp_faultlab.report import render
from mcp_faultlab.verify import compare_paths


class ProductTests(unittest.TestCase):
    def test_redaction_covers_keys_and_token_patterns(self):
        value = {"api_key": "secret", "nested": "Bearer abcdefghijklmnop", "text": "sk-abcdefghijklmnop"}
        result = redact(value)
        self.assertEqual(result["api_key"], "[REDACTED]")
        self.assertNotIn("abcdefghijklmnop", result["nested"])
        self.assertNotIn("sk-abcdefghijklmnop", result["text"])

    def test_engine_matches_tool_occurrence(self):
        engine = FaultEngine([FaultRule(kind="tool_error", tool="search", occurrence=2)])
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search"}}
        self.assertEqual(engine.observe(request), [])
        self.assertEqual(len(engine.observe(request)), 1)

    def test_campaign_mutates_response(self):
        cassette = new_cassette("demo")
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search"}}
        response = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"text": "fresh"}]}}
        add_event(cassette, "client->server", request, request_sequence=10)
        add_event(cassette, "server->client", response, request_sequence=10)
        variant = apply_rules(cassette, parse_rules({"kind": "stale_data", "tool": "search", "replacement": "old"}))
        self.assertEqual(variant["events"][1]["message"]["result"]["content"][0]["text"], "old")
        self.assertEqual(variant["events"][1]["message_before_fault"]["result"]["content"][0]["text"], "fresh")

    def test_verify_ignores_runtime_metadata(self):
        left = new_cassette("one")
        right = new_cassette("two")
        message_left = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        message_right = {"jsonrpc": "2.0", "id": 99, "method": "initialize"}
        add_event(left, "client->server", message_left)
        add_event(right, "client->server", message_right)
        with tempfile.TemporaryDirectory() as directory:
            a = Path(directory) / "a.json"
            b = Path(directory) / "b.json"
            a.write_text(json.dumps(left), encoding="utf-8")
            b.write_text(json.dumps(right), encoding="utf-8")
            ok, _ = compare_paths(str(a), str(b))
            self.assertTrue(ok)

    def test_report_contains_fault_and_before_after(self):
        cassette = new_cassette("demo")
        add_event(cassette, "server->client", {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}, fault="tool_error", message_before_fault={"ok": False})
        report = render(cassette)
        self.assertIn("tool_error", report)
        self.assertIn("Before fault", report)
        self.assertIn("timeline", report)
