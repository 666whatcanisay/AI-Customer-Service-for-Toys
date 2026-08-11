from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "simulators" / "pdd-customer-workspace"


def test_simulator_exposes_observer_and_controlled_send_dom_contract() -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert 'currentuid="sim-customer-a01"' in html
    assert 'id="msgListContainer"' in html
    assert 'id="replyTextarea"' in html
    assert 'class="send-btn"' in html
    assert 'class="commonCard product-context"' in html
    assert 'class="good-content"' in html
    assert 'id="right-panel"' in html
    assert 'class="order-item"' in html


def test_simulator_uses_only_synthetic_business_data() -> None:
    content = "\n".join(
        (SITE / name).read_text(encoding="utf-8")
        for name in ("index.html", "styles.css", "app.js")
    )
    assert "SIM-STORE-001" in content
    assert "SIM-PRODUCT-001" in content
    assert "SIM-SKU-AGE8-CHAMPAGNE" in content
    assert "8岁以上" in content
    assert "mms.pinduoduo.com" not in content
    assert "Cookie" not in content
    assert "password" not in content.casefold()


def test_simulator_requires_human_confirmation_and_has_no_network_client() -> None:
    javascript = (SITE / "app.js").read_text(encoding="utf-8")
    assert "openConfirmation" in javascript
    assert "confirmSyntheticSend" in javascript
    assert "会话发生变化，已拒绝仿真发送" in javascript
    assert "window.__PDD_SIMULATOR__" in javascript
    assert "synthetic-pdd-contract.v1" in javascript
    assert "externalSendEnabled: false" in javascript
    assert "product: PRODUCT" in javascript
    assert "sku: SKU" in javascript
    assert "order: ORDER" in javascript
    assert "fetch(" not in javascript
    assert "WebSocket" not in javascript


def test_simulator_server_is_loopback_only_and_declares_no_external_send() -> None:
    runner = (ROOT / "scripts" / "run_pdd_workspace_simulator.py").read_text(
        encoding="utf-8"
    )
    assert 'default="127.0.0.1"' in runner
    assert '"external_send_enabled": False' in runner
    assert '"real_platform_connected": False' in runner
    assert '"contract_version": "synthetic-pdd-contract.v1"' in runner
    assert "connect-src 'none'" in runner
