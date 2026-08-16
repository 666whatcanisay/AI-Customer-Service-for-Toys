from __future__ import annotations

import argparse
import sys

import httpx

from channel_agent.control_v2 import ServiceRequestSigner
from channel_agent.security import WindowsDeviceCredentialStore


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the signed AI-CS -> Host Control V2 device link."
    )
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--ca-certificate", required=True)
    parser.add_argument("--service-id", required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--credential-reference", required=True)
    args = parser.parse_args()

    path = "/channel-agent/v2/service/agents"
    secret = WindowsDeviceCredentialStore().acquire(
        args.credential_reference
    ).for_signing()
    signer = ServiceRequestSigner(args.service_id, args.key_id, secret)
    try:
        response = httpx.get(
            args.server_url.rstrip("/") + path,
            headers=signer.headers("GET", path),
            verify=args.ca_certificate,
            timeout=5.0,
            trust_env=False,
        )
    except httpx.HTTPError as exc:
        print(f"HOST_CONTROL_UNREACHABLE:{type(exc).__name__}", file=sys.stderr)
        return 2
    if response.status_code != 200:
        print(f"SIGNED_DEVICE_QUERY_REJECTED:{response.status_code}", file=sys.stderr)
        return 3
    try:
        payload = response.json()
        if payload.get("authoritative_source") != "CHANNEL_ENGINE_HOST_CONTROL":
            raise ValueError("authoritative source mismatch")
        for item in payload.get("items", []):
            if item.get("identity_status") not in {
                "REGISTERED",
                "BOUND",
                "ACTIVE",
                "DISABLED",
            }:
                raise ValueError("identity status is not V2.1")
            if item.get("connectivity_status") not in {"ONLINE", "OFFLINE"}:
                raise ValueError("connectivity status is not V2.1")
    except (TypeError, ValueError) as exc:
        print(f"SIGNED_DEVICE_RESPONSE_INVALID:{exc}", file=sys.stderr)
        return 4
    print("SIGNED_DEVICE_LINK_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
