import json
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(__file__))


def cli(*args, cwd=ROOT, env=None):
    command_env = os.environ.copy()
    command_env["PYTHONPATH"] = ROOT
    if env:
        command_env.update(env)
    return subprocess.run([sys.executable, "-m", "mcp_faultlab", *args], cwd=cwd, env=command_env, text=True, capture_output=True)


class CliTests(unittest.TestCase):
    def test_version_and_pack_listing(self):
        version = cli("--version")
        packs = cli("packs")
        self.assertEqual(version.returncode, 0)
        self.assertEqual(version.stdout.strip(), "0.4.1")
        self.assertGreaterEqual(len(packs.stdout.splitlines()), 10)

    def test_run_report_replay_and_github_summary(self):
        with tempfile.TemporaryDirectory() as output:
            summary = os.path.join(output, "summary.md")
            result = cli("run", "examples/tool-timeout-recovery.yml", "--out", output, env={"GITHUB_STEP_SUMMARY": summary})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("3 passed", result.stdout)
            run_json = os.path.join(output, "tool-timeout-recovery.run.json")
            cassette = os.path.join(output, "tool-timeout-recovery.cassette.json")
            report = os.path.join(output, "tool-timeout-recovery.html")
            self.assertTrue(os.path.exists(run_json))
            self.assertTrue(os.path.exists(cassette))
            self.assertTrue(os.path.exists(report))
            with open(summary, encoding="utf-8") as summary_file:
                self.assertIn("Assertion", summary_file.read())
            replay = cli("replay", cassette, "--json")
            self.assertEqual(replay.returncode, 0, replay.stderr)
            self.assertEqual(json.loads(replay.stdout.splitlines()[0])["status"], "recoverable")
            regenerated = cli("report", run_json)
            self.assertEqual(regenerated.returncode, 0, regenerated.stderr)

    def test_security_scenario_fails_ci(self):
        with tempfile.TemporaryDirectory() as output:
            result = cli("run", "examples/malicious-tool-result.yml", "--out", output)
            self.assertEqual(result.returncode, 1)
            self.assertIn("security violation", result.stdout)

    def test_directory_run_aggregates_scenarios(self):
        with tempfile.TemporaryDirectory() as directory:
            suite = os.path.join(directory, "suite")
            output = os.path.join(suite, "faultlab-report")
            os.makedirs(suite)
            demo = os.path.join(ROOT, "examples", "demo_server.py")
            scenario = os.path.join(suite, "timeout.yml")
            with open(scenario, "w", encoding="utf-8") as handle:
                handle.write("""name: batch-timeout\ntarget:\n  command: %s %s\nrequests:\n  - id: 1\n    method: tools/call\n    params:\n      name: search\nfaults:\n  - kind: timeout\n    method: tools/call\nassertions:\n  - final_status: recoverable\n""" % (sys.executable, demo))
            safe = os.path.join(suite, "safe.yml")
            safe_agent = os.path.join(ROOT, "examples", "safe_agent.py")
            server = os.path.join(ROOT, "examples", "demo_server.py")
            with open(safe, "w", encoding="utf-8") as handle:
                handle.write("""name: batch-safe\nagent:\n  command: %s\nserver:\n  command: %s\nattacks:\n  - tool_result_prompt_injection\nassertions:\n  - no_dangerous_tool_call\n""" % ("%s %s" % (sys.executable, safe_agent), "%s %s" % (sys.executable, server)))
            result = cli("run", suite, "--out", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("2 passed", result.stdout)
            with open(os.path.join(output, "campaign.json"), encoding="utf-8") as handle:
                summary = json.load(handle)
            self.assertEqual(summary["scenario_count"], 2)
            self.assertTrue(summary["passed"])
            self.assertTrue(os.path.exists(os.path.join(output, "campaign.html")))
            second = cli("run", suite, "--out", output)
            self.assertEqual(second.returncode, 0, second.stderr)
            with open(os.path.join(output, "campaign.json"), encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["scenario_count"], 2)

    def test_invalid_scenario_is_a_short_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "bad.yml")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("name: bad\nassertions:\n  - does_not_exist\n")
            result = cli("validate", path)
            self.assertEqual(result.returncode, 1)
            self.assertIn("target.command is required", result.stdout)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
