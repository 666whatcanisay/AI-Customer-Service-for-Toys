from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from channel_engine.production_operations_app import create_operations_console_app


def test_18020_is_a_fail_closed_client_of_authoritative_host_control(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv(
        "CHANNEL_ENGINE_OPERATIONS_DATABASE_URL",
        f"sqlite:///{(tmp_path / 'operations.sqlite3').as_posix()}",
    )
    monkeypatch.setenv("CHANNEL_ENGINE_AI_CS_ADMIN_URL", "http://127.0.0.1:9")
    app = create_operations_console_app()

    assert app.state.production_profile == "OPERATIONS_CONSOLE_CLIENT"
    assert app.state.device_repository_authority is False
    assert not any(
        getattr(route, "path", "").startswith("/channel-agent/v1")
        for route in app.routes
    )

    with TestClient(
        app,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 52000),
    ) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert (
            health.json()["device_state_source"]
            == "CHANNEL_ENGINE_HOST_CONTROL_VIA_AI_CS"
        )

        listing = client.get("/ops/devices")
        assert listing.status_code == 401
        assert listing.json()["detail"] == "OPS_ADMIN_LOGIN_REQUIRED"

        session = client.get("/ops/admin/session")
        assert session.status_code == 200
        assert session.json() == {
            "authenticated": False,
            "status": "SIGNED_OUT",
            "username": None,
            "display_name": None,
            "reason": "OPS_ADMIN_LOGIN_REQUIRED",
        }

        blocked_write = client.post(
            "/ops/devices/agent-001/disable",
            headers={
                "Origin": "http://127.0.0.1",
                "X-Operator-Intent": "HUMAN_CONFIRMED_AGENT_DISABLE",
            },
            json={
                "reason": "测试正式控制台在无管理员会话时安全阻断",
                "confirmation_text": "确认禁用设备",
            },
        )
        assert blocked_write.status_code == 401
        assert blocked_write.json()["detail"] == "OPS_ADMIN_LOGIN_REQUIRED"


def test_18020_issues_admin_confirmed_enrollment_grant_via_ai_cs_only(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv(
        "CHANNEL_ENGINE_OPERATIONS_DATABASE_URL",
        f"sqlite:///{(tmp_path / 'operations-grant.sqlite3').as_posix()}",
    )
    monkeypatch.setenv("CHANNEL_ENGINE_AI_CS_ADMIN_URL", "http://127.0.0.1:8422")

    def login(*args, **kwargs):
        return httpx.Response(200, json={
            "access_token": "opaque-admin-token",
            "expires_at": "2099-08-08T00:00:00+00:00",
            "user": {
                "username": "admin",
                "display_name": "运营管理员",
                "roles": ["ADMIN"],
                "permissions": ["user.manage"],
            },
        }, request=httpx.Request("POST", "http://127.0.0.1:8422/api/v1/auth/login"))

    calls: list[dict[str, object]] = []

    def upstream(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        if str(url).endswith("/binding-targets"):
            payload = {
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
                "checked_at": "2026-08-08T09:00:00+00:00",
            }
            return httpx.Response(200, json=payload, request=httpx.Request(method, url))
        if str(url).endswith("/host/pairing-codes/rotate"):
            payload = {
                "schema_version": "ai-cs.customer-desktop-workflow.v1",
                "host_id": "host-001",
                "pairing_code": "7K3M9Q2X4T8R",
                "expires_at": "2026-08-08T09:05:00+00:00",
                "display_once": True,
            }
            return httpx.Response(201, json=payload, request=httpx.Request(method, url))
        payload = {
            "schema_version": "ai-cs.customer-desktop-workflow.v1",
            "grant_id": "grant-001",
            "agent_id": "agent-001",
            "device_id": "device-001",
            "user_reference": "11111111-1111-4111-8111-111111111111",
            "store_references": ["STORE-007"],
            "binding_code": "ABCDEF0123456789ABCDEF0123456789",
            "issued_at": "2026-08-08T09:00:00+00:00",
            "expires_at": "2026-08-08T09:10:00+00:00",
        }
        return httpx.Response(201, json=payload, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "post", login)
    monkeypatch.setattr(httpx, "request", upstream)
    app = create_operations_console_app()
    with TestClient(
        app,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 52000),
    ) as client:
        authenticated = client.post(
            "/ops/admin/session/login",
            headers={"Origin": "http://127.0.0.1"},
            json={"username": "admin", "password": "not-persisted"},
        )
        assert authenticated.status_code == 200
        session = client.get("/ops/admin/session")
        assert session.status_code == 200
        assert session.json() == {
            "authenticated": True,
            "status": "AUTHENTICATED",
            "username": "admin",
            "display_name": "运营管理员",
            "reason": None,
        }
        targets = client.get("/ops/devices/binding-targets")
        assert targets.status_code == 200
        assert targets.json()["items"][0]["stores"][0]["store_code"] == "STORE-007"

        missing_intent = client.post(
            "/ops/devices/agent-001/enrollment-grants",
            headers={"Origin": "http://127.0.0.1"},
            json={
                "user_id": "11111111-1111-4111-8111-111111111111",
                "store_ids": [7],
                "reason": "管理员确认客服电脑首次人工绑定",
                "confirmation_text": "确认生成设备绑定许可",
            },
        )
        assert missing_intent.status_code == 403

        granted = client.post(
            "/ops/devices/agent-001/enrollment-grants",
            headers={
                "Origin": "http://127.0.0.1",
                "X-Operator-Intent": "HUMAN_CONFIRMED_ENROLLMENT_GRANT",
            },
            json={
                "user_id": "11111111-1111-4111-8111-111111111111",
                "store_ids": [7],
                "reason": "管理员确认客服电脑首次人工绑定",
                "confirmation_text": "确认生成设备绑定许可",
            },
        )
        assert granted.status_code == 201
        assert granted.headers["cache-control"] == "no-store"
        assert granted.json()["binding_code"] == "ABCDEF0123456789ABCDEF0123456789"
        assert calls[-1]["headers"] == {"Authorization": "Bearer opaque-admin-token"}

        missing_rotation_intent = client.post(
            "/ops/devices/host-pairing-code/rotate",
            headers={"Origin": "http://127.0.0.1"},
            json={
                "reason": "新客服电脑首次安装连接可信主机",
                "confirmation_text": "确认重新生成主机连接码",
            },
        )
        assert missing_rotation_intent.status_code == 403

        rotated = client.post(
            "/ops/devices/host-pairing-code/rotate",
            headers={
                "Origin": "http://127.0.0.1",
                "X-Operator-Intent": "HUMAN_CONFIRMED_HOST_PAIRING_CODE_ROTATION",
            },
            json={
                "reason": "新客服电脑首次安装连接可信主机",
                "confirmation_text": "确认重新生成主机连接码",
            },
        )
        assert rotated.status_code == 201
        assert rotated.headers["cache-control"] == "no-store"
        assert rotated.headers["pragma"] == "no-cache"
        assert rotated.json()["pairing_code"] == "7K3M9Q2X4T8R"
        assert calls[-1]["url"].endswith("/host/pairing-codes/rotate")
