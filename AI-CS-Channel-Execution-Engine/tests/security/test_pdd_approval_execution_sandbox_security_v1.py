from __future__ import annotations

import inspect

from channel_engine.execution import (
    FakePDDExecutor,
    PDDApprovalExecutionTrace,
    PDDApprovalSandboxSafetySnapshot,
    PDDHumanApprovalExecutionSandbox,
)


def test_sandbox_has_no_automatic_approval_or_real_transport_path() -> None:
    runtime_source = inspect.getsource(PDDHumanApprovalExecutionSandbox)
    executor_source = inspect.getsource(FakePDDExecutor)

    assert "auto_approve" not in runtime_source
    assert "run_until_idle" not in runtime_source
    assert "http://" not in executor_source
    assert "https://" not in executor_source
    assert "cookie" not in executor_source.lower()
    assert "customer_message_sent\": True" not in executor_source
    assert "real_platform_called\": True" not in executor_source


def test_trace_and_safety_models_exclude_customer_content_and_credentials() -> None:
    forbidden = {
        "content",
        "customer_message",
        "cookie",
        "token",
        "password",
        "credential_ref",
        "address",
        "phone",
        "payment_details",
    }

    assert forbidden.isdisjoint(PDDApprovalExecutionTrace.model_fields)
    assert forbidden.isdisjoint(PDDApprovalSandboxSafetySnapshot.model_fields)
