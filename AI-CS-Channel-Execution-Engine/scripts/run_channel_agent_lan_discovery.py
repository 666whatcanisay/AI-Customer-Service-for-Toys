from __future__ import annotations

import argparse
import json
import os
import signal
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

from channel_agent.control_v2 import (
    LANDiscoveryResponder,
    LANHostCandidate,
    PairingError,
    decode_pairing_credential,
)
from channel_agent.security import WindowsDeviceCredentialStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve signed Channel Agent LAN discovery.")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--port", type=int, default=18421)
    args = parser.parse_args()
    pairing_reference = os.getenv(
        "CHANNEL_ENGINE_AGENT_PAIRING_CREDENTIAL_REFERENCE", ""
    ).strip()
    legacy_code = os.getenv("CHANNEL_ENGINE_AGENT_PAIRING_CODE", "").strip()
    if not pairing_reference and not legacy_code:
        raise SystemExit("pairing credential reference is required")
    credential_store = WindowsDeviceCredentialStore()

    def pairing_code() -> str:
        if not pairing_reference:
            return legacy_code
        credential = decode_pairing_credential(
            credential_store.acquire(pairing_reference).for_signing()
        )
        if credential.expires_at <= datetime.now(UTC):
            raise PairingError("pairing credential expired")
        return credential.pairing_code
    source = Path(args.candidate).resolve()
    if not source.is_file() or source.stat().st_size > 65_536:
        raise SystemExit("candidate file is unavailable")
    candidate = LANHostCandidate.model_validate(json.loads(source.read_text(encoding="utf-8")))
    stop = Event()

    def request_stop(*_args: object) -> None:
        stop.set()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        value = getattr(signal, name, None)
        if value is not None:
            signal.signal(value, request_stop)
    LANDiscoveryResponder(
        candidate=candidate,
        pairing_code_provider=pairing_code,
        port=args.port,
    ).serve(stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
