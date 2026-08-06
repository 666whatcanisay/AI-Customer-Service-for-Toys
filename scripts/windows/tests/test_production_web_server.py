from __future__ import annotations

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest


SERVER_PATH = Path(__file__).resolve().parents[1] / "serve_ai_cs_web.py"
SPEC = importlib.util.spec_from_file_location("serve_ai_cs_web", SERVER_PATH)
assert SPEC and SPEC.loader
web = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(web)


class UpstreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        return

    def do_GET(self):
        payload = json.dumps({
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "internal_service_token": self.headers.get("X-AI-CS-Service-Token"),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Request-ID", "upstream-request")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class ProductionWebServerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name).resolve()
        (root / "index.html").write_text("<html>production</html>", encoding="utf-8")
        assets = root / "assets"
        assets.mkdir()
        (assets / "app-deadbeef.js").write_text("console.log('ok')", encoding="utf-8")

        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        self.upstream_thread = Thread(target=self.upstream.serve_forever, daemon=True)
        self.upstream_thread.start()
        origin = f"http://127.0.0.1:{self.upstream.server_port}"

        self.server = web.ProductionWebServer(
            ("127.0.0.1", 0),
            web.Handler,
            root=root,
            proxies=[("/platform-api", origin)],
            allowed_hosts={"127.0.0.1", "localhost"},
            max_body=1024,
        )
        self.server_thread = Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.upstream.shutdown()
        self.upstream.server_close()
        self.temporary.cleanup()

    def request(self, method: str, path: str, headers=None):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3
        )
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        payload = response.read()
        result = response.status, dict(response.getheaders()), payload
        connection.close()
        return result

    def test_static_assets_have_production_security_and_cache_headers(self):
        status, headers, payload = self.request("GET", "/assets/app-deadbeef.js")
        self.assertEqual(status, 200)
        self.assertIn(b"console.log", payload)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Strict-Transport-Security"], "max-age=31536000")
        self.assertIn("immutable", headers["Cache-Control"])
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_proxy_is_allowlisted_and_forwards_only_expected_identity_headers(self):
        status, headers, payload = self.request(
            "GET",
            "/platform-api/health?check=1",
            headers={
                "Authorization": "Bearer synthetic",
                "Cookie": "must-not-forward",
                "X-AI-CS-Service-Token": "must-not-forward",
            },
        )
        body = json.loads(payload)
        self.assertEqual(status, 200)
        self.assertEqual(body["path"], "/health?check=1")
        self.assertEqual(body["authorization"], "Bearer synthetic")
        self.assertIsNone(body["internal_service_token"])
        self.assertEqual(headers["X-Request-ID"], "upstream-request")

    def test_host_header_and_path_traversal_fail_closed(self):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3
        )
        connection.putrequest("GET", "/", skip_host=True)
        connection.putheader("Host", "attacker.example")
        connection.endheaders()
        response = connection.getresponse()
        response.read()
        self.assertEqual(response.status, 400)
        connection.close()

        status, _, _ = self.request("GET", "/%2e%2e/private.secret")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
