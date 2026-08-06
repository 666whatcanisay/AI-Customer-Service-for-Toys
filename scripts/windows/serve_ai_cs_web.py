"""Small production static server with an explicit loopback proxy allowlist."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
import mimetypes
from pathlib import Path
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


LOG = logging.getLogger("ai_cs.production_web")
REQUEST_HEADERS = {
    "accept",
    "authorization",
    "content-type",
    "idempotency-key",
    "x-request-id",
}
RESPONSE_HEADERS = {
    "cache-control",
    "content-disposition",
    "content-type",
    "etag",
    "idempotency-replayed",
    "last-modified",
    "x-request-id",
}
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    ),
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


def loopback_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise argparse.ArgumentTypeError("proxy origins must be loopback HTTP roots")
    return value.rstrip("/")


def proxy_mapping(value: str) -> tuple[str, str]:
    prefix, separator, origin = value.partition("=")
    if separator != "=" or not prefix.startswith("/") or prefix == "/":
        raise argparse.ArgumentTypeError("proxy must use /prefix=http://loopback:port")
    normalized = prefix.rstrip("/")
    if any(part in {"", ".", ".."} for part in normalized.split("/")[1:]):
        raise argparse.ArgumentTypeError("proxy prefix is invalid")
    return normalized, loopback_origin(origin)


class ProductionWebServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    request_queue_size = 128

    def __init__(self, address, handler, *, root, proxies, allowed_hosts, max_body):
        super().__init__(address, handler)
        self.root = root
        self.proxies = dict(proxies)
        self.allowed_hosts = frozenset(item.casefold() for item in allowed_hosts)
        self.max_body = max_body
        self.opener = build_opener(ProxyHandler({}), NoRedirect())


class Handler(BaseHTTPRequestHandler):
    server: ProductionWebServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format_string: str, *args) -> None:
        LOG.info("client=%s %s", self.client_address[0], format_string % args)

    def _security_headers(self) -> None:
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)

    def _host_allowed(self) -> bool:
        raw_host = self.headers.get("Host", "")
        try:
            parsed = urlsplit(f"//{raw_host}")
            host = (parsed.hostname or "").casefold()
        except ValueError:
            return False
        return host in self.server.allowed_hosts

    def _error(self, status: HTTPStatus, message: str) -> None:
        payload = message.encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _proxy_target(self, path: str) -> tuple[str, str] | None:
        for prefix, origin in self.server.proxies.items():
            if path == prefix or path.startswith(f"{prefix}/"):
                suffix = path[len(prefix):] or "/"
                return prefix, f"{origin}{suffix}"
        return None

    def _proxy(self, target: str, query: str) -> None:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            content_length = int(raw_length)
        except ValueError:
            self._error(HTTPStatus.BAD_REQUEST, "Invalid Content-Length")
            return
        if content_length < 0 or content_length > self.server.max_body:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request body is too large")
            return
        body = self.rfile.read(content_length) if content_length else None
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.casefold() in REQUEST_HEADERS
        }
        request = Request(
            f"{target}{'?' + query if query else ''}",
            data=body,
            headers=headers,
            method=self.command,
        )
        try:
            response = self.server.opener.open(request, timeout=180)
        except HTTPError as exc:
            response = exc
        except (URLError, TimeoutError):
            self._error(HTTPStatus.BAD_GATEWAY, "Upstream service is unavailable")
            return
        try:
            payload = response.read()
            self.send_response(response.status)
            for name, value in response.headers.items():
                if name.casefold() in RESPONSE_HEADERS:
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self._security_headers()
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        finally:
            response.close()

    def _static(self, path: str) -> None:
        try:
            decoded = unquote(path, errors="strict")
        except UnicodeError:
            self._error(HTTPStatus.BAD_REQUEST, "Invalid path")
            return
        if "\x00" in decoded:
            self._error(HTTPStatus.BAD_REQUEST, "Invalid path")
            return
        relative = decoded.lstrip("/") or "index.html"
        candidate = (self.server.root / relative).resolve()
        try:
            candidate.relative_to(self.server.root)
        except ValueError:
            self._error(HTTPStatus.NOT_FOUND, "Not found")
            return
        if not candidate.is_file():
            accepts_html = "text/html" in self.headers.get("Accept", "")
            if accepts_html and "." not in Path(relative).name:
                candidate = self.server.root / "index.html"
            else:
                self._error(HTTPStatus.NOT_FOUND, "Not found")
                return
        payload = candidate.read_bytes()
        content_type, _ = mimetypes.guess_type(candidate.name)
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header(
            "Cache-Control",
            "public, max-age=31536000, immutable"
            if relative.startswith("assets/")
            else "no-cache",
        )
        self._security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _handle(self) -> None:
        if not self._host_allowed():
            self._error(HTTPStatus.BAD_REQUEST, "Host is not allowed")
            return
        parsed = urlsplit(self.path)
        proxy = self._proxy_target(parsed.path)
        if proxy is not None:
            self._proxy(proxy[1], parsed.query)
        elif self.command in {"GET", "HEAD"}:
            self._static(parsed.path)
        else:
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "Method is not allowed")

    do_GET = _handle
    do_HEAD = _handle
    do_POST = _handle
    do_PUT = _handle
    do_PATCH = _handle
    do_DELETE = _handle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bind-address", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--proxy", action="append", type=proxy_mapping, default=[])
    parser.add_argument("--allowed-host", action="append", default=[])
    parser.add_argument("--max-body-bytes", type=int, default=32 * 1024 * 1024)
    parser.add_argument("--tls-cert", type=Path)
    parser.add_argument("--tls-key", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve(strict=True)
    if not (root / "index.html").is_file():
        raise SystemExit("static root must contain index.html")
    if not 1 <= args.port <= 65535 or args.max_body_bytes < 1:
        raise SystemExit("port/body limit is invalid")
    if bool(args.tls_cert) != bool(args.tls_key):
        raise SystemExit("TLS certificate and key must be configured together")
    allowed_hosts = {
        args.bind_address,
        "127.0.0.1",
        "localhost",
        "::1",
        *args.allowed_host,
    }
    server = ProductionWebServer(
        (args.bind_address, args.port),
        Handler,
        root=root,
        proxies=args.proxy,
        allowed_hosts=allowed_hosts,
        max_body=args.max_body_bytes,
    )
    if args.tls_cert and args.tls_key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.tls_cert, args.tls_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    LOG.info("production web ready bind=%s port=%s root=%s", args.bind_address, args.port, root)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
