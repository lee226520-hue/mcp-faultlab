import unittest

from mcp_faultlab.faults import Fault


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
