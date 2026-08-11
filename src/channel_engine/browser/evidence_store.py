from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from channel_engine.storage.orm import SelectorEvidenceRow

from .selectors import (
    SelectorCapability,
    SelectorContract,
    SelectorContractDrift,
    SelectorContractState,
    SelectorEvidenceEnvironment,
)


class SelectorEvidenceConflict(RuntimeError):
    pass


class SelectorEvidenceStore:
    """Immutable durable evidence registry used by runtime selector gates."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    def record(self, contract: SelectorContract, *, activate: bool = False) -> None:
        evidence = contract.verification_evidence
        if contract.state is not SelectorContractState.VERIFIED or evidence is None:
            raise SelectorEvidenceConflict("only evidence-backed VERIFIED selectors can be stored")
        if evidence.selector_set_hash != contract.selector_set_hash():
            raise SelectorEvidenceConflict(
                "durable selector evidence does not bind the complete selector set"
            )
        payload = contract.model_dump(mode="json")
        with self._sessions() as session:
            existing = session.get(SelectorEvidenceRow, evidence.evidence_hash)
            if existing is not None:
                if existing.contract_json != payload:
                    raise SelectorEvidenceConflict("selector evidence hash is immutable")
                if activate and not existing.active:
                    self._activate(session, contract, evidence.evidence_hash)
                    session.commit()
                return
            if activate:
                self._deactivate_page(session, contract.platform, contract.page)
            session.add(
                SelectorEvidenceRow(
                    evidence_hash=evidence.evidence_hash,
                    evidence_reference=evidence.reference,
                    platform=contract.platform,
                    page=contract.page,
                    version=contract.version,
                    environment=evidence.environment.value,
                    page_fingerprint=evidence.page_fingerprint,
                    applicable_page_version=evidence.applicable_page_version,
                    capabilities=sorted(item.value for item in evidence.capability_boundary),
                    contract_json=payload,
                    verified_by=evidence.verified_by,
                    verified_at=evidence.verified_at,
                    expires_at=evidence.expires_at,
                    active=activate,
                )
            )
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise SelectorEvidenceConflict(
                    "selector contract version or evidence reference already exists"
                ) from exc

    def active(
        self,
        *,
        platform: str,
        page: str,
        environment: SelectorEvidenceEnvironment,
        page_fingerprint: str,
        capability: SelectorCapability,
        now: datetime,
    ) -> SelectorContract:
        with self._sessions() as session:
            row = session.scalar(
                select(SelectorEvidenceRow).where(
                    SelectorEvidenceRow.platform == platform,
                    SelectorEvidenceRow.page == page,
                    SelectorEvidenceRow.active.is_(True),
                )
            )
            if row is None:
                raise SelectorContractDrift("active selector evidence is unavailable")
            contract = SelectorContract.model_validate_json(
                json.dumps(row.contract_json, separators=(",", ":"))
            )
        contract.assert_runtime_evidence(
            page_fingerprint=page_fingerprint,
            environment=environment,
            now=now,
            capability=capability,
        )
        if (
            contract.verification_evidence is None
            or contract.verification_evidence.evidence_hash != row.evidence_hash
        ):
            raise SelectorContractDrift("stored selector evidence hash changed")
        return contract

    @staticmethod
    def _deactivate_page(session: Session, platform: str, page: str) -> None:
        session.execute(
            update(SelectorEvidenceRow)
            .where(
                SelectorEvidenceRow.platform == platform,
                SelectorEvidenceRow.page == page,
            )
            .values(active=False)
        )

    def _activate(
        self,
        session: Session,
        contract: SelectorContract,
        evidence_hash: str,
    ) -> None:
        self._deactivate_page(session, contract.platform, contract.page)
        session.execute(
            update(SelectorEvidenceRow)
            .where(SelectorEvidenceRow.evidence_hash == evidence_hash)
            .values(active=True)
        )


__all__ = ["SelectorEvidenceConflict", "SelectorEvidenceStore"]
