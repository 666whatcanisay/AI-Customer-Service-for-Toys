from __future__ import annotations

import ast
from pathlib import Path

import pytest

from channel_engine.conversation import ConversationService
from channel_engine.models import DecisionState
from channel_engine.pdd_adapter import (
    FakePDDAdapter,
    PDDBrowserAdapter,
    PDDPrototypeSessionRuntime,
    PDDPrototypeUnavailable,
    PDDSelectorState,
)
from channel_engine.session import (
    ChannelInstanceManager,
    ChannelSessionStore,
    CredentialReference,
    FakeCredentialProvider,
    MessageReliabilityService,
)

from .helpers import message_envelope, verified_selector_token


def connected_pdd_session(foundation):
    session_store = ChannelSessionStore(foundation["uow_factory"])
    reference = CredentialReference(
        credential_ref="vault://offline-pdd-prototype/integration-store",
        provider="offline-vault",
        version="v1",
    )
    manager = ChannelInstanceManager(
        session_store,
        FakeCredentialProvider((reference,)),
        MessageReliabilityService(foundation["uow_factory"], session_store),
    )
    runtime = PDDPrototypeSessionRuntime(manager)
    created = runtime.create(
        store_id="synthetic-store-1",
        credential_ref=reference,
        instance_id="pdd-prototype-integration-instance",
    )
    return runtime.start(created.instance_id)


def test_fake_pdd_to_conversation_to_decision_stops_at_human_approval(foundation) -> None:
    token = verified_selector_token()
    adapter = FakePDDAdapter(
        store_id="synthetic-store-1",
        selector_token=token,
    )
    adapter.open_session(connected_pdd_session(foundation))
    observed = message_envelope(token=token)
    adapter.enqueue_observation(observed)
    adapter.enqueue_observation(observed)

    messages = adapter.receive_messages()

    assert len(messages) == 1
    assert adapter.duplicate_count == 1
    assert adapter.received_count == 1
    assert adapter.health_check().details["write_capability_enabled"] is False
    assert adapter.health_check().real_platform_connected is False
    conversation = adapter.get_conversation(messages[0].conversation_id)
    assert conversation is not None
    assert conversation.message_count == 1

    result = ConversationService(
        foundation["uow_factory"], foundation["gateway"]
    ).receive(messages[0].to_runtime_message())

    assert result.decision_state is DecisionState.WAITING_APPROVAL
    assert result.requires_approval is True
    assert foundation["gateway"].call_count == 1
    assert foundation["executor"].call_count == 0
    with foundation["uow_factory"]() as uow:
        assert (
            uow.require_repository().get_execution_for_decision(result.decision_id)
            is None
        )


def test_fake_pdd_fails_closed_for_unverified_selector_and_page_failure(
    foundation,
) -> None:
    token = verified_selector_token()
    adapter = FakePDDAdapter(
        store_id="synthetic-store-1",
        selector_token=token,
    )
    adapter.open_session(connected_pdd_session(foundation))
    adapter.enqueue_observation(message_envelope(token=token))
    adapter.simulate_selector_state(PDDSelectorState.DISCOVERY)
    with pytest.raises(PDDPrototypeUnavailable, match="not VERIFIED"):
        adapter.receive_messages()

    adapter.simulate_selector_state(PDDSelectorState.VERIFIED)
    adapter.simulate_page_unavailable()
    with pytest.raises(PDDPrototypeUnavailable, match="page is unavailable"):
        adapter.receive_messages()


def test_public_prototype_has_no_platform_write_or_business_mutation_surface() -> None:
    forbidden = {
        "send_message",
        "click_send",
        "submit",
        "execute",
        "refund",
        "modify_order",
        "update_order",
    }
    assert forbidden.isdisjoint(dir(FakePDDAdapter))
    assert forbidden.isdisjoint(dir(PDDBrowserAdapter))

    package_root = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "channel_engine"
        / "pdd_adapter"
    )
    defined_functions: set[str] = set()
    for path in package_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        defined_functions.update(
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
    assert forbidden.isdisjoint(defined_functions)
