import os
import io
import json
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest

from mcp_faultlab.assertions import evaluate
from mcp_faultlab.runner import run_scenario
from mcp_faultlab.replay import serve
from mcp_faultlab.proxy import create_http_server
from mcp_faultlab.redaction import redact
from mcp_faultlab.scenario import load_scenario, validate_scenario
from mcp_faultlab.yamlite import loads


ROOT = os.path.dirname(os.path.dirname(__file__))


class MvpTests(unittest.TestCase):
    def test_yaml_scenario_loads_inline_map(self):
        scenario = load_scenario(os.path.join(ROOT, "examples", "tool-timeout-recovery.yml"))
        self.assertEqual(scenario["requests"][0]["params"]["arguments"]["q"], "faultlab")

    def test_timeout_is_recoverable(self):
        scenario = load_scenario(os.path.join(ROOT, "examples", "tool-timeout-recovery.yml"))
        result = run_scenario(scenario)
        self.assertTrue(result["passed"])
        self.assertEqual(result["status"], "recoverable")

    def test_security_pack_is_evidence(self):
        scenario = load_scenario(os.path.join(ROOT, "examples", "tool-timeout-recovery.yml"))
        scenario["faults"] = [{"kind": "sensitive_result", "method": "tools/call"}]
        scenario["assertions"] = ["no_security_violation"]
        result = run_scenario(scenario)
        self.assertTrue(result["passed"])
        self.assertEqual(result["attack_injections"], 1)
        self.assertEqual(result["security_violations"], 0)

    def test_agent_proxy_catches_prompt_injection_followed_by_shell(self):
        scenario = load_scenario(os.path.join(ROOT, "examples", "agent-prompt-injection.yml"))
        result = run_scenario(scenario)
        self.assertFalse(result["passed"])
        self.assertEqual(result["metrics"]["tool_call_count"], 2)
        self.assertEqual(result["security_violations"], 1)

    def test_agent_proxy_allows_safe_agent(self):
        scenario = load_scenario(os.path.join(ROOT, "examples", "agent-prompt-injection-safe.yml"))
        result = run_scenario(scenario)
        self.assertTrue(result["passed"])
        self.assertEqual(result["attack_injections"], 1)
        self.assertEqual(result["security_violations"], 0)

    def test_reports_redact_credential_values_but_assertions_see_them(self):
        scenario = load_scenario(os.path.join(ROOT, "examples", "tool-timeout-recovery.yml"))
        scenario["faults"] = [{"kind": "sensitive_result", "method": "tools/call", "security": True, "result": {"content": "api_key=supersecret"}}]
        scenario["assertions"] = ["no_sensitive_data_in_results"]
        result = run_scenario(scenario)
        self.assertFalse(result["assertions"][0]["passed"])
        self.assertNotIn("supersecret", json.dumps(result["events"]))
        self.assertIn("<redacted>", json.dumps(result["events"]))

    def test_redaction_covers_json_strings_and_bearer_tokens(self):
        value = '{"api_key": "supersecret", "authorization": "Bearer abc.def"}'
        safe = redact(value)
        self.assertNotIn("supersecret", safe)
        self.assertNotIn("abc.def", safe)
        self.assertIn("<redacted>", safe)

    def test_assertion_unknown_fails_closed(self):
        result = evaluate(["made_up_assertion"], [])
        self.assertFalse(result[0]["passed"])

    def test_run_exposes_metrics(self):
        scenario = load_scenario(os.path.join(ROOT, "examples", "tool-timeout-recovery.yml"))
        result = run_scenario(scenario)
        self.assertEqual(result["metrics"]["tool_call_count"], 1)
        self.assertIn("estimated_tokens", result["metrics"])

    def test_validate_rejects_unknown_assertion(self):
        scenario = load_scenario(os.path.join(ROOT, "examples", "tool-timeout-recovery.yml"))
        scenario["assertions"] = ["made_up_assertion"]
        self.assertTrue(validate_scenario(scenario))

    def test_replay_server_returns_recorded_response(self):
        cassette = {"events": [{"type": "response", "id": 7, "response_kind": "target", "response": {"result": {"ok": True}}}]}
        input_stream = io.StringIO(json.dumps({"id": 7, "method": "tools/call"}) + "\n")
        output_stream = io.StringIO()
        serve(cassette, input_stream, output_stream)
        self.assertEqual(json.loads(output_stream.getvalue())["result"]["ok"], True)

    def test_replay_strictly_rejects_same_id_with_different_request(self):
        cassette = {"events": [
            {"type": "request", "id": 7, "method": "tools/call", "params": {"name": "safe"}},
            {"type": "response", "id": 7, "response_kind": "target", "response": {"result": {"ok": True}}},
        ]}
        output_stream = io.StringIO()
        serve(cassette, io.StringIO(json.dumps({"id": 7, "method": "tools/call", "params": {"name": "dangerous"}}) + "\n"), output_stream)
        self.assertEqual(json.loads(output_stream.getvalue())["error"]["code"], "REPLAY_MISMATCH")

    def test_replay_strictly_rejects_unknown_request_id(self):
        cassette = {"events": [
            {"type": "request", "id": 7, "method": "tools/call", "params": {"name": "safe"}},
            {"type": "response", "id": 7, "response_kind": "target", "response": {"result": {"ok": True}}},
        ]}
        output_stream = io.StringIO()
        serve(cassette, io.StringIO(json.dumps({"id": 99, "method": "tools/call", "params": {"name": "safe"}}) + "\n"), output_stream)
        self.assertEqual(json.loads(output_stream.getvalue())["error"]["code"], "REPLAY_MISS")

    def test_yaml_comments_and_nested_lists(self):
        value = loads("""name: sample\nitems:\n  - name: one\n    enabled: true # comment\n""")
        self.assertEqual(value["items"][0]["enabled"], True)

    def test_yaml_inline_values_keep_nested_commas(self):
        value = loads('params: {query: "a, b", filters: [one, two], nested: {enabled: true}}')
        self.assertEqual(value["params"]["query"], "a, b")
        self.assertEqual(value["params"]["filters"], ["one", "two"])
        self.assertEqual(value["params"]["nested"]["enabled"], True)

    def test_target_response_timeout_is_bounded(self):
        scenario = {
            "name": "hung-target",
            "target": {"command": "%s %s" % (sys.executable, os.path.join(ROOT, "examples", "hanging_server.py")), "response_timeout_ms": 40},
            "requests": [{"id": 1, "method": "tools/call", "params": {"name": "slow"}}],
            "faults": [],
            "assertions": [{"final_status": "recoverable"}],
        }
        result = run_scenario(scenario)
        self.assertEqual(result["status"], "recoverable")
        self.assertEqual(result["events"][1]["response_kind"], "timeout")
        self.assertLess(result["duration_ms"], 1000)

    def test_target_response_size_is_bounded(self):
        scenario = {
            "name": "large-target",
            "target": {"command": "%s %s" % (sys.executable, os.path.join(ROOT, "examples", "large_server.py")), "max_response_bytes": 1024},
            "requests": [{"id": 1, "method": "tools/call", "params": {"name": "large"}}],
            "faults": [],
            "assertions": [{"final_status": "recoverable"}],
        }
        result = run_scenario(scenario)
        self.assertEqual(result["events"][1]["response_kind"], "error")
        self.assertIn("too large", result["events"][1]["response"]["error"])

    def test_http_proxy_forwards_and_injects(self):
        class Upstream(BaseHTTPRequestHandler):
            calls = 0

            def do_POST(self):
                Upstream.calls += 1
                response = json.dumps({"id": 1, "result": {"from": "upstream"}}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, *_args):
                return

        try:
            upstream_server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        except PermissionError:
            self.skipTest("sandbox does not allow local socket binding")
        upstream_thread = threading.Thread(target=upstream_server.serve_forever, daemon=True)
        upstream_thread.start()
        upstream_url = "http://127.0.0.1:%d" % upstream_server.server_address[1]
        proxy_server, events = create_http_server("127.0.0.1:0", upstream_url, [{"kind": "tool_result_prompt_injection", "method": "tools/call", "security": True}])
        proxy_thread = threading.Thread(target=proxy_server.serve_forever, daemon=True)
        proxy_thread.start()
        proxy_url = "http://127.0.0.1:%d" % proxy_server.server_address[1]
        try:
            def post(payload):
                request = urllib.request.Request(proxy_url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(request, timeout=2) as response:
                    return json.loads(response.read().decode("utf-8"))

            forwarded = post({"id": 1, "method": "tools/list", "params": {}})
            injected = post({"id": 2, "method": "tools/call", "params": {"name": "search"}})
            self.assertEqual(forwarded["result"]["from"], "upstream")
            self.assertIn("SYSTEM", injected["result"]["content"])
            self.assertEqual(Upstream.calls, 1)
            self.assertEqual(len([event for event in events if event.get("type") == "request"]), 2)
            self.assertTrue(any(event.get("attack_injected") for event in events))
        finally:
            proxy_server.shutdown()
            proxy_server.server_close()
            upstream_server.shutdown()
            upstream_server.server_close()


if __name__ == "__main__":
    unittest.main()
