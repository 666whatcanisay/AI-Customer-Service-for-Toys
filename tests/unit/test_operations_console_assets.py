from __future__ import annotations

from channel_engine.observability.ui import (
    OPERATIONS_CONSOLE_CSS,
    OPERATIONS_CONSOLE_HTML,
    OPERATIONS_CONSOLE_JS,
    OPERATIONS_CONSOLE_UI_VERSION,
)


def test_operations_console_has_all_product_modules_and_safety_boundary() -> None:
    assert OPERATIONS_CONSOLE_UI_VERSION == "1.3"
    assert "AI-CS 智能客服运营控制中心" in OPERATIONS_CONSOLE_HTML
    for view in (
        "overview",
        "trace",
        "approvals",
        "executions",
        "channels",
        "devices",
        "recovery",
    ):
        assert f'id="view-{view}"' in OPERATIONS_CONSOLE_HTML
    for label in (
        "运行总览",
        "会话流程追踪",
        "人工审核中心",
        "执行审计记录",
        "店铺与渠道",
        "问题诊断与恢复",
    ):
        assert label in OPERATIONS_CONSOLE_HTML
    assert "必须人工审核" in OPERATIONS_CONSOLE_HTML
    assert "自动执行已关闭" in OPERATIONS_CONSOLE_HTML
    assert "设备管理" in OPERATIONS_CONSOLE_HTML
    assert "/ops/assets/operations-console.css?v=1.3.6" in OPERATIONS_CONSOLE_HTML
    assert "/ops/assets/operations-console.js?v=1.3.6" in OPERATIONS_CONSOLE_HTML
    assert "中文控制台 V1.3" in OPERATIONS_CONSOLE_HTML
    assert 'id="device-admin-status"' in OPERATIONS_CONSOLE_HTML
    assert 'id="device-admin-login"' in OPERATIONS_CONSOLE_HTML
    assert "登录管理员并读取设备" in OPERATIONS_CONSOLE_HTML
    assert "<style" not in OPERATIONS_CONSOLE_HTML
    assert "<script>" not in OPERATIONS_CONSOLE_HTML


def test_console_api_adapter_and_dom_rendering_are_fail_closed() -> None:
    assert "/ops/console/snapshot" in OPERATIONS_CONSOLE_JS
    assert "/ops/devices" in OPERATIONS_CONSOLE_JS
    assert "adminSession()" in OPERATIONS_CONSOLE_JS
    assert "登录运营管理员后读取 18443 权威设备状态" in OPERATIONS_CONSOLE_JS
    assert "const capture = promise" in OPERATIONS_CONSOLE_JS
    assert "HUMAN_CONFIRMED_AGENT_UNBIND" in OPERATIONS_CONSOLE_JS
    assert "HUMAN_CONFIRMED_AGENT_DISABLE" in OPERATIONS_CONSOLE_JS
    assert "HUMAN_CONFIRMED_ENROLLMENT_GRANT" in OPERATIONS_CONSOLE_JS
    assert "/ops/devices/binding-targets" in OPERATIONS_CONSOLE_JS
    assert "重新生成12位主机连接码" in OPERATIONS_CONSOLE_HTML
    assert "生成32位账号绑定许可" in OPERATIONS_CONSOLE_HTML
    assert "HUMAN_CONFIRMED_HOST_PAIRING_CODE_ROTATION" in OPERATIONS_CONSOLE_JS
    assert "/ops/devices/host-pairing-code/rotate" in OPERATIONS_CONSOLE_JS
    assert "新的12位主机连接码" in OPERATIONS_CONSOLE_HTML
    assert "32位账号绑定许可" in OPERATIONS_CONSOLE_HTML
    assert "/session-runtime/v1/instances" in OPERATIONS_CONSOLE_JS
    assert "/ops/recoveries?limit=100" in OPERATIONS_CONSOLE_JS
    assert "/ops/approvals/" in OPERATIONS_CONSOLE_JS
    assert "/review`" in OPERATIONS_CONSOLE_JS
    assert "HUMAN_ACTION_REVIEWED_NO_AUTOMATIC_EXECUTION" in OPERATIONS_CONSOLE_JS
    assert "APPROVE" in OPERATIONS_CONSOLE_JS
    assert "REJECT" in OPERATIONS_CONSOLE_JS
    assert "只创建一条“待执行”任务" in OPERATIONS_CONSOLE_JS
    assert "客户问题" in OPERATIONS_CONSOLE_JS
    assert "AI 建议" in OPERATIONS_CONSOLE_JS
    assert "知识来源" in OPERATIONS_CONSOLE_JS
    assert "风险等级" in OPERATIONS_CONSOLE_JS
    assert "未标注（按需人工复核）" in OPERATIONS_CONSOLE_JS
    assert "stateChip = status =>" in OPERATIONS_CONSOLE_JS
    assert "statusLabel(status)" in OPERATIONS_CONSOLE_JS
    for source, localized in (
        ("HEALTHY", "正常"),
        ("UNHEALTHY", "异常"),
        ("RUNNING", "运行中"),
        ("WAITING_APPROVAL", "待人工审核"),
        ("UNKNOWN", "结果待确认"),
    ):
        assert f"{source}: '{localized}'" in OPERATIONS_CONSOLE_JS
    for step in (
        "客户消息",
        "AI 分析",
        "回复建议",
        "人工确认",
        "受控执行",
        "结果凭证",
    ):
        assert step in OPERATIONS_CONSOLE_JS
    assert "innerHTML" not in OPERATIONS_CONSOLE_JS
    assert "textContent" in OPERATIONS_CONSOLE_JS
    assert OPERATIONS_CONSOLE_CSS.count("{") == OPERATIONS_CONSOLE_CSS.count("}")
    assert "--sidebar" in OPERATIONS_CONSOLE_CSS
    assert ".trace-flow" in OPERATIONS_CONSOLE_CSS
    assert ".state-chip.UNKNOWN" in OPERATIONS_CONSOLE_CSS


def _relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def test_console_uses_light_mint_theme_with_accessible_state_colors() -> None:
    assert '<meta name="color-scheme" content="light">' in OPERATIONS_CONSOLE_HTML
    assert "color-scheme:light" in OPERATIONS_CONSOLE_CSS
    assert "--bg:#edf8f1" in OPERATIONS_CONSOLE_CSS
    assert ".sidebar{background:#12372c" in OPERATIONS_CONSOLE_CSS
    assert ".state-chip.OFFLINE" in OPERATIONS_CONSOLE_CSS
    assert ".state-chip.REGISTERED" in OPERATIONS_CONSOLE_CSS
    assert "Black metallic status surfaces v1.3.6" in OPERATIONS_CONSOLE_CSS
    assert ".state-chip.ACTIVE:before" in OPERATIONS_CONSOLE_CSS
    assert ".state-chip.RUNNING:before" in OPERATIONS_CONSOLE_CSS
    assert ".state-chip.REGISTERED:before" in OPERATIONS_CONSOLE_CSS
    assert ".state-chip.WAITING_BINDING:before" in OPERATIONS_CONSOLE_CSS
    assert ".state-chip.DEGRADED:before" in OPERATIONS_CONSOLE_CSS
    assert ".state-chip.DISABLED:before" in OPERATIONS_CONSOLE_CSS
    assert ".state-chip.WARNING:before" in OPERATIONS_CONSOLE_CSS
    assert ".state-chip.STOPPED:before" in OPERATIONS_CONSOLE_CSS
    for foreground, background in (
        ("#17352a", "#edf8f1"),  # primary text on the mint workspace
        ("#f3f6f4", "#22292d"),  # status text on the metallic surface
    ):
        assert _contrast_ratio(foreground, background) >= 4.5
    for indicator in ("#39d98a", "#4bb8ff", "#f0b84a", "#ff625c", "#a9b4bf"):
        assert _contrast_ratio(indicator, "#080b0d") >= 3.0
