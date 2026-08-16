from __future__ import annotations

from datetime import datetime, timedelta, timezone

from channel_engine.channel import (
    ChannelAuthenticationScheme,
    ChannelCredentialReference,
    FakePDDCredentialProvider,
    FakePDDOutboundTransport,
    FakePDDProductionObservationTransport,
    InMemoryPDDObservationLedger,
    LedgerExecutionAuthorizationService,
    PDDOutboundMode,
    PDDProductionPolicyConfig,
    PDDProductionSendPolicy,
    ProductionPDDAdapter,
)


class ProductionClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


def production_credential(
    version: str = "production-preparation-v1",
) -> ChannelCredentialReference:
    return ChannelCredentialReference(
        credential_id="secret-manager/pdd/production-account",
        provider="secret-manager",
        version=version,
        account_ref="pdd-production-preparation-account",
        auth_scheme=ChannelAuthenticationScheme.MANAGED_SESSION,
    )


def build_production_adapter(
    foundation,
    clock: ProductionClock,
    *,
    conversations: frozenset[str] = frozenset({"pdd-production-conversation"}),
    outbound_mode: PDDOutboundMode = PDDOutboundMode.SUCCESS,
    credential: ChannelCredentialReference | None = None,
    provider: FakePDDCredentialProvider | None = None,
    observation: FakePDDProductionObservationTransport | None = None,
    ledger: InMemoryPDDObservationLedger | None = None,
):
    active_credential = credential or production_credential()
    active_provider = provider or FakePDDCredentialProvider(clock=clock)
    if provider is None:
        active_provider.register(
            active_credential,
            expires_at=clock() + timedelta(hours=1),
        )
    active_observation = observation or FakePDDProductionObservationTransport(
        clock=clock
    )
    active_ledger = ledger or InMemoryPDDObservationLedger()
    outbound = FakePDDOutboundTransport(outbound_mode, clock=clock)
    authorization = LedgerExecutionAuthorizationService(
        foundation["uow_factory"],
        clock=clock,
    )
    policy = PDDProductionSendPolicy(
        PDDProductionPolicyConfig(
            allowed_account_refs=frozenset({active_credential.account_ref}),
            allowed_conversation_ids=conversations,
        )
    )
    adapter = ProductionPDDAdapter(
        active_credential,
        active_provider,
        active_observation,
        outbound,
        active_ledger,
        authorization,
        policy,
        clock=clock,
    )
    return (
        adapter,
        active_provider,
        active_observation,
        outbound,
        active_ledger,
        authorization,
    )
