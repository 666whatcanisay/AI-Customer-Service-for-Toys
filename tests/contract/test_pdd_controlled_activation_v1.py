from __future__ import annotations

from channel_engine.pdd_adapter import (
    PDD_ACTIVATION_GATE_ORDER,
    PDD_CONTROLLED_ACTIVATION_STATUS,
    PDD_CONTROLLED_ACTIVATION_VERSION,
    PDDControlledActivationCheckInput,
)


def test_controlled_activation_contract_is_versioned_and_has_fixed_gate_order() -> None:
    schema = PDDControlledActivationCheckInput.model_json_schema()

    assert PDD_CONTROLLED_ACTIVATION_VERSION == "1.0"
    assert PDD_CONTROLLED_ACTIVATION_STATUS == "PDD_CONTROLLED_ACTIVATION_READY"
    assert [gate.value for gate in PDD_ACTIVATION_GATE_ORDER] == [
        "PREFLIGHT",
        "CREDENTIAL_CHECK",
        "RBAC_CHECK",
        "SELECTOR_CHECK",
        "OBSERVATION_MODE",
        "HUMAN_APPROVAL",
    ]
    assert schema["title"] == "PDDControlledActivationCheckInput"
    assert "plan" in schema["required"]
    assert "transport" in schema["required"]
    assert "runtime" in schema["required"]
    assert "gateway" in schema["required"]
    assert "safety" in schema["required"]


def test_contract_contains_no_action_or_secret_payload_field() -> None:
    schema = PDDControlledActivationCheckInput.model_json_schema()

    def property_names(value) -> set[str]:
        if isinstance(value, dict):
            result = set(value.get("properties", {}))
            for nested in value.values():
                result.update(property_names(nested))
            return result
        if isinstance(value, list):
            result: set[str] = set()
            for nested in value:
                result.update(property_names(nested))
            return result
        return set()

    fields = {name.casefold() for name in property_names(schema)}

    for prohibited_field in (
        "cookie_value",
        "token_value",
        "password_value",
        "message_content",
        "send_message",
        "click_send",
        "activation_grant_payload",
    ):
        assert prohibited_field not in fields
