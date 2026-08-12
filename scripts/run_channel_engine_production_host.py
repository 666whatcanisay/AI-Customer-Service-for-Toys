from __future__ import annotations

import argparse
import os

import uvicorn

from channel_engine.agent.tls import HostTLSConfiguration, is_loopback_bind_address


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the production Host Control app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    options: dict[str, object] = {}
    tls_configured = bool(
        os.getenv("CHANNEL_ENGINE_TLS_CERTIFICATE", "").strip()
        or os.getenv("CHANNEL_ENGINE_TLS_PRIVATE_KEY", "").strip()
    )
    if not is_loopback_bind_address(args.host) or tls_configured:
        tls = HostTLSConfiguration.from_environment()
        options.update(
            ssl_certfile=str(tls.certificate_path),
            ssl_keyfile=str(tls.private_key_path),
            ssl_keyfile_password=tls.password(),
        )
    # The runtime profile intentionally rejects private-key material in the
    # Channel Engine environment.  A non-loopback listener has already resolved
    # the encrypted key into Uvicorn options.  In either case these
    # launcher-only values must not reach the
    # subsequently imported application configuration.
    os.environ.pop("CHANNEL_ENGINE_TLS_PRIVATE_KEY", None)
    os.environ.pop("CHANNEL_ENGINE_TLS_PRIVATE_KEY_CREDENTIAL_REFERENCE", None)
    uvicorn.run(
        "channel_engine.production_app:create_host_control_app",
        host=args.host,
        port=args.port,
        reload=False,
        access_log=False,
        factory=True,
        **options,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
