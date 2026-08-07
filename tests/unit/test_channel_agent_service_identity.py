from __future__ import annotations

from pathlib import Path

import pytest

from channel_engine.security.rbac import (
    FileBackedAgentOperatorIdentityProvider,
    OperatorAccessDenied,
    OperatorRole,
)


REFERENCE = "r030-unit-reference-0123456789-abcdef"


def write_reference(path: Path, value: str = REFERENCE) -> Path:
    path.write_text(value, encoding="utf-8")
    return path


def test_file_backed_agent_service_identity_accepts_only_exact_reference(
    tmp_path: Path,
) -> None:
    provider = FileBackedAgentOperatorIdentityProvider(
        write_reference(tmp_path / "agent.session"),
        principal_id="ai-cs-agent-service-test",
    )

    principal = provider.authenticate(REFERENCE)

    assert principal.principal_id == "ai-cs-agent-service-test"
    assert principal.roles == frozenset({OperatorRole.ADMIN})
    assert principal.identity_provider == "agent-service-file"
    assert REFERENCE not in repr(provider.__dict__)
    with pytest.raises(OperatorAccessDenied):
        provider.authenticate(f"{REFERENCE}-wrong")


@pytest.mark.parametrize(
    "value",
    ["too-short", f"{REFERENCE}\nsecond-line"],
)
def test_file_backed_agent_service_identity_rejects_invalid_reference_file(
    tmp_path: Path,
    value: str,
) -> None:
    with pytest.raises(ValueError, match="reference file is invalid"):
        FileBackedAgentOperatorIdentityProvider(
            write_reference(tmp_path / "invalid.session", value)
        )


def test_file_backed_agent_service_identity_requires_absolute_existing_path(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="path must be absolute"):
        FileBackedAgentOperatorIdentityProvider(Path("relative.session"))
    with pytest.raises(ValueError, match="file is unavailable"):
        FileBackedAgentOperatorIdentityProvider(tmp_path / "missing.session")


def test_file_backed_agent_service_identity_validates_principal_at_startup(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError):
        FileBackedAgentOperatorIdentityProvider(
            write_reference(tmp_path / "agent.session"),
            principal_id="invalid principal with spaces",
        )
