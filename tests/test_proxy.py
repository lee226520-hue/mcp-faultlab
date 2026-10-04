import json
import sys
import unittest
from io import StringIO
from pathlib import Path

from mcp_faultlab.proxy import run_proxy
from mcp_faultlab.faults import FaultRule


class ProxyTests(unittest.TestCase):
    def test_correlates_out_of_order_responses(self):
        root = Path(__file__).resolve().parents[1]
        incoming = StringIO(
            '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"a"}}\n'
            '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"b"}}\n'
        )
        output = StringIO()
        run_proxy(f"{sys.executable} {root / 'examples' / 'concurrent_server.py'}", stdin=incoming, stdout=output)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual({response["id"] for response in responses}, {1, 2})
        self.assertEqual([response["id"] for response in responses], [2, 1])

    def test_delay_fault_does_not_block_other_responses(self):
        root = Path(__file__).resolve().parents[1]
        incoming = StringIO(
            '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"a"}}\n'
            '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"b"}}\n'
        )
        output = StringIO()
        run_proxy(
            f"{sys.executable} {root / 'examples' / 'concurrent_server.py'}",
            rules=[FaultRule(kind="timeout", tool="a", delay_ms=120)],
            stdin=incoming,
            stdout=output,
        )
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([response["id"] for response in responses], [2, 1])
