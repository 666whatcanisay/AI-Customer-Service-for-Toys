from __future__ import annotations

import argparse
import secrets

from channel_agent.security import (
    DeviceCredentialStore,
    DeviceCredentialUnavailable,
    WindowsDeviceCredentialStore,
)


def ensure_service_credential(
    credential_reference: str,
    *,
    store: DeviceCredentialStore | None = None,
) -> bool:
    """Ensure a shared service key exists without ever returning its value.

    Returns ``True`` only when a new credential was created. Existing material is
    deliberately reused so restarting either service does not invalidate the other.
    """

    credential_store = store or WindowsDeviceCredentialStore()
    try:
        credential_store.acquire(credential_reference)
        return False
    except DeviceCredentialUnavailable:
        credential_store.put(credential_reference, secrets.token_bytes(48))
        # Read after write so an ACL or persistence failure stops startup now.
        credential_store.acquire(credential_reference)
        return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Provision the AI-CS to Channel Engine service credential."
    )
    parser.add_argument("--credential-reference", required=True)
    args = parser.parse_args()
    created = ensure_service_credential(args.credential_reference)
    print("CREATED" if created else "READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
