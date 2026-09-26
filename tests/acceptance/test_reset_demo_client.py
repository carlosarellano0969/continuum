from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts import reset_demo


class RecordingHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        self.__class__.requests.append(
            {
                "method": "POST",
                "path": self.path,
                "body": body,
                "organization_id": self.headers.get("X-Organization-ID"),
                "agent_id": self.headers.get("X-Agent-ID"),
            }
        )
        payload = {"counts": {"memories": 6}, "active_policy_version": 1}
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        return


class ResetDemoClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RecordingHandler.requests = []
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        host, port = cls.server.server_address
        cls.base_url = f"http://{host}:{port}/api"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_reset_request_uses_contract_path_body_and_scope_headers(self):
        payload = reset_demo._request(
            self.base_url,
            "/demo/reset",
            method="POST",
            timeout=2,
            organization_id="demo-org",
            agent_id="demo-agent",
            body={"seed": 20260924},
        )
        self.assertEqual(payload["active_policy_version"], 1)
        self.assertEqual(
            RecordingHandler.requests[-1],
            {
                "method": "POST",
                "path": "/api/demo/reset",
                "body": {"seed": 20260924},
                "organization_id": "demo-org",
                "agent_id": "demo-agent",
            },
        )


if __name__ == "__main__":
    unittest.main()
