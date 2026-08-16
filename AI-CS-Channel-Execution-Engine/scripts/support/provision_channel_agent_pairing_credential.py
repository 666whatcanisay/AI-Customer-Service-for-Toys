from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta

from channel_agent.control_v2 import encode_pairing_credential, normalize_pairing_code
from channel_agent.security import WindowsDeviceCredentialStore


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Store a short-lived host pairing code in Windows Credential Manager."
    )
    parser.add_argument("--credential-reference", required=True)
    parser.add_argument("--expires-in-seconds", type=int, default=300)
    args = parser.parse_args()
    if not 30 <= args.expires_in_seconds <= 900:
        raise SystemExit("pairing credential lifetime is invalid")
    code = normalize_pairing_code(sys.stdin.readline().strip())
    expires_at = datetime.now(UTC) + timedelta(seconds=args.expires_in_seconds)
    WindowsDeviceCredentialStore().put(
        args.credential_reference,
        encode_pairing_credential(code, expires_at),
    )
    # Never echo the pairing code. The caller already owns the one-time display.
    print(expires_at.isoformat())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
