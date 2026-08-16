from __future__ import annotations

import inspect

from channel_engine.pdd_adapter import (
    PDDControlledActivationPlan,
    PDDControlledActivationPreflight,
)


def test_offline_preflight_exposes_no_runtime_action_method() -> None:
    public_methods = {
        name
        for name, value in inspect.getmembers(
            PDDControlledActivationPreflight,
            predicate=inspect.isfunction,
        )
        if not name.startswith("_")
    }

    assert public_methods == {"evaluate"}
    for prohibited in (
        "connect",
        "open",
        "start",
        "login",
        "poll",
        "receive",
        "send",
        "execute",
        "issue_grant",
    ):
        assert prohibited not in public_methods


def test_plan_schema_hard_codes_no_activation_no_send_and_no_message_read() -> None:
    properties = PDDControlledActivationPlan.model_json_schema()["properties"]

    assert properties["real_platform_activation_allowed"]["const"] is False
    assert properties["real_send_enabled"]["const"] is False
    assert properties["customer_message_read_allowed_by_plan"]["const"] is False
    assert properties["activation_grant_issued"]["const"] is False
