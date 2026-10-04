import json
import tempfile
import unittest
from pathlib import Path

from mcp_faultlab.cassette import add_event, new_cassette, save
from mcp_faultlab.replay import serve


class ReplayTests(unittest.TestCase):
    def test_replay_rewrites_request_id(self):
        cassette = new_cassette("demo")
        add_event(cassette, "client->server", {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        add_event(
            cassette,
            "server->client",
            {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.json"
            save(path, cassette)

            from io import StringIO

            output = StringIO()
            serve(str(path), StringIO('{"jsonrpc":"2.0","id":99,"method":"initialize"}\n'), output)
            self.assertEqual(json.loads(output.getvalue())["id"], 99)
