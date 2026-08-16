from __future__ import annotations

import argparse
import json
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class SimulatorHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            payload = json.dumps(
                {
                    "service": "pdd-customer-workspace-simulator",
                    "version": "1.1",
                    "contract_version": "synthetic-pdd-contract.v1",
                    "synthetic_only": True,
                    "real_platform_connected": False,
                    "external_send_enabled": False,
                },
                separators=(",", ":"),
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'none'; object-src 'none'",
        )
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Run the synthetic PDD workspace simulator")
    result.add_argument("--bind", default="127.0.0.1")
    result.add_argument("--port", type=int, default=8431)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.bind not in {"127.0.0.1", "localhost"}:
        raise SystemExit("simulator must remain loopback-only")
    site_root = Path(__file__).resolve().parents[1] / "simulators" / "pdd-customer-workspace"
    handler = partial(SimulatorHandler, directory=str(site_root))
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
