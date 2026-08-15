from __future__ import annotations

import json
from datetime import UTC, datetime

from channel_agent.binding import atomic_write_bytes
from channel_agent.controlled_auto_runtime import ControlledAutoRuntimeStateStore
from scripts.run_controlled_pdd_reply_pilot import (
    _consume_desktop_toggle,
    _renew_observer_if_needed,
)


def _write_agent_state(data_root, *, observer_status: str = "OBSERVING") -> None:
    runtime = data_root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "channel-agent-state.json").write_text(
        json.dumps({
            "identity_status": "ACTIVE",
            "pdd_login_state": "CUSTOMER_SERVICE_READY",
            "observer_status": observer_status,
            "active_store_id": "c-store-1",
            "pdd_store_id": "328616090",
        }),
        encoding="utf-8",
    )


def _queue_toggle(data_root, target_enabled: bool) -> None:
    atomic_write_bytes(
        data_root / "runtime" / "controlled-auto-toggle.request",
        json.dumps({
            "schema_version": "controlled-auto-toggle-request.v1",
            "target_enabled": target_enabled,
            "operator_reference": "desktop-local-operator",
            "human_intent": True,
            "requested_at": datetime.now(UTC).isoformat(),
        }).encode("utf-8"),
    )


def test_desktop_toggle_pauses_and_resumes_same_verified_scope(tmp_path) -> None:
    _write_agent_state(tmp_path)
    store = ControlledAutoRuntimeStateStore(tmp_path / "runtime.sqlite3")
    store.activate_production_auto(
        ai_cs_store_id="c-store-1",
        platform_store_id="328616090",
        policy_revision=2,
        whitelist_revision="auto-all-v1",
        operator="operator",
        reason="activate",
        policy_mode="AUTO_ALL_MESSAGES_V1",
    )

    _queue_toggle(tmp_path, False)
    paused, error = _consume_desktop_toggle(tmp_path, store)
    assert error is None
    assert paused.production_real_send_enabled is False
    assert paused.kill_switch_enabled is True
    assert paused.ai_cs_store_id == "c-store-1"
    assert paused.platform_store_id == "328616090"

    _queue_toggle(tmp_path, True)
    resumed, error = _consume_desktop_toggle(tmp_path, store)
    assert error is None
    assert resumed.runtime_mode == "PRODUCTION_AUTO"
    assert resumed.production_real_send_enabled is True
    assert resumed.controlled_store_auto_enabled is True
    assert resumed.kill_switch_enabled is False


def test_production_auto_renews_expired_read_observer(tmp_path) -> None:
    _write_agent_state(tmp_path, observer_status="SESSION_LIMIT_REACHED")

    _renew_observer_if_needed(tmp_path)

    payload = json.loads(
        (tmp_path / "runtime" / "pdd-observer-restart.request").read_text(
            encoding="utf-8"
        )
    )
    assert payload["human_intent"] is True
    assert payload["reason"] == "PRODUCTION_AUTO_OBSERVER_SESSION_RENEWAL"
