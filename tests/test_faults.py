import unittest

from mcp_faultlab.faults import ATTACK_PACKS, Fault, parse_rules


class FaultTests(unittest.TestCase):
    def test_tool_error_mutation(self):
        response = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"text": "ok"}]}}
        mutated = Fault(kind="tool_error", message="boom").mutate(response)
        self.assertTrue(mutated["result"]["isError"])
        self.assertEqual(mutated["result"]["content"][0]["text"], "boom")
        self.assertEqual(response["result"]["content"][0]["text"], "ok")


    def test_stale_data_mutation(self):
        response = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"text": "fresh"}]}}
        mutated = Fault(kind="stale_data", replacement="old").mutate(response)
        self.assertEqual(mutated["result"]["content"][0]["text"], "old")

    def test_all_attack_packs_expand_and_mutate(self):
        self.assertEqual(len(ATTACK_PACKS), 10)
        for name in ATTACK_PACKS:
            rules = parse_rules({"attacks": [name]})
            self.assertEqual(rules[0].kind, name)
            response = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"text": "fresh"}]}}
            if name == "infinite_retry":
                with self.assertRaises(Exception):
                    rules[0].mutate(response)
            else:
                mutated = rules[0].mutate(response)
                self.assertIsInstance(mutated, dict)

    def test_faults_and_attacks_can_be_combined(self):
        rules = parse_rules({"faults": [{"kind": "stale_data"}], "attacks": ["fake_success"]})
        self.assertEqual([rule.kind for rule in rules], ["stale_data", "fake_success"])

    def test_description_attack_changes_tool_description(self):
        response = {"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "search", "description": "safe"}]}}
        mutated = parse_rules({"attacks": ["tool_description_prompt_injection"]})[0].mutate(response)
        self.assertIn("Ignore safety", mutated["result"]["tools"][0]["description"])
