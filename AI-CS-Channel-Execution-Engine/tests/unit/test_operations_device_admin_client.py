from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from channel_engine.observability.device_admin_client import HttpAICSDeviceAdminClient


def _response(status_code: int, payload: object) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request("GET", "http://127.0.0.1:8422/test"),
    )


def test_admin_binding_targets_and_one_time_grant_are_strictly_forwarded(
    monkeypatch,
) -> None:
    now = datetime.now(UTC)
    calls: list[dict[str, object]] = []

    def request(method: str, url: str, **kwargs: object) -> httpx.Response:
        calls.append({"method": method, "url": url, **kwargs})
        if url.endswith("/binding-targets"):
            return _response(200, {
                "items": [{
                    "user_id": "11111111-1111-4111-8111-111111111111",
                    "username": "support.agent",
                    "display_name": "验收客服",
                    "stores": [{
                        "store_id": 7,
                        "store_code": "STORE-007",
                        "store_name": "测试店铺",
                        "platform": "PDD",
                        "is_default": True,
                    }],
                }],
                "count": 1,
                "checked_at": now.isoformat(),
            })
        if url.endswith("/host/pairing-codes/rotate"):
            return _response(201, {
                "schema_version": "ai-cs.customer-desktop-workflow.v1",
                "host_id": "host-001",
                "pairing_code": "7K3M9Q2X4T8R",
                "expires_at": (now + timedelta(minutes=5)).isoformat(),
                "display_once": True,
            })
        return _response(201, {
            "schema_version": "ai-cs.customer-desktop-workflow.v1",
            "grant_id": "grant-001",
            "agent_id": "agent-001",
            "device_id": "device-001",
            "user_reference": "11111111-1111-4111-8111-111111111111",
            "store_references": ["STORE-007"],
            "binding_code": "ABCDEF0123456789ABCDEF0123456789",
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
        })

    monkeypatch.setattr(httpx, "request", request)
    client = HttpAICSDeviceAdminClient("http://127.0.0.1:8422")

    targets = client.list_binding_targets("opaque-admin-token")
    assert targets.items[0].stores[0].store_code == "STORE-007"
    grant = client.issue_enrollment_grant(
        "opaque-admin-token",
        "agent-001",
        user_id="11111111-1111-4111-8111-111111111111",
        store_ids=(7,),
        reason="管理员确认客服电脑首次人工绑定",
    )
    assert grant.binding_code == "ABCDEF0123456789ABCDEF0123456789"
    assert "ABCDEF" not in repr(grant)
    assert calls[1]["json"] == {
        "user_id": "11111111-1111-4111-8111-111111111111",
        "store_ids": [7],
        "reason": "管理员确认客服电脑首次人工绑定",
        "confirmation_phrase": "确认生成设备绑定许可",
    }
    assert calls[1]["headers"] == {"Authorization": "Bearer opaque-admin-token"}

    pairing = client.rotate_host_pairing_code(
        "opaque-admin-token",
        "新客服电脑首次安装连接可信主机",
    )
    assert pairing.pairing_code == "7K3M9Q2X4T8R"
    assert "7K3M9Q2X4T8R" not in repr(pairing)
    assert calls[2]["url"].endswith("/api/v1/admin/desktop-workflow/host/pairing-codes/rotate")
    assert calls[2]["json"] == {
        "reason": "新客服电脑首次安装连接可信主机",
        "confirmation_phrase": "确认重新生成主机连接码",
    }
