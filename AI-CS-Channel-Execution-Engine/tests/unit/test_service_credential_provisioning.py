from __future__ import annotations

import importlib.util
from pathlib import Path

from channel_agent.security import InMemoryDeviceCredentialStore


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "support" / "provision_channel_agent_service_credential.py"


def _module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("service_credential_provisioning", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_service_credential_is_created_once_and_reused() -> None:
    module = _module()
    store = InMemoryDeviceCredentialStore()
    reference = "wincred://AI-CS/ChannelEngine/test/AI-CSService"

    assert module.ensure_service_credential(reference, store=store) is True
    first = store.acquire(reference).for_signing()
    assert module.ensure_service_credential(reference, store=store) is False
    assert store.acquire(reference).for_signing() == first
    assert len(first) >= 32
