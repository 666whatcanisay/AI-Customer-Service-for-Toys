from __future__ import annotations

from channel_engine.observability.ui import (
    OPERATIONS_CONSOLE_CSS,
    OPERATIONS_CONSOLE_HTML,
    OPERATIONS_CONSOLE_JS,
    OPERATIONS_CONSOLE_UI_VERSION,
)


def test_operations_console_has_all_product_modules_and_safety_boundary() -> None:
    assert OPERATIONS_CONSOLE_UI_VERSION == "1.1"
    assert "AI-CS 智能客服运营控制中心" in OPERATIONS_CONSOLE_HTML
    for view in (
        "overview",
        "trace",
        "approvals",
        "executions",
        "channels",
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
    assert "/ops/assets/operations-console.css?v=1.1" in OPERATIONS_CONSOLE_HTML
    assert "/ops/assets/operations-console.js?v=1.1" in OPERATIONS_CONSOLE_HTML
    assert "<style" not in OPERATIONS_CONSOLE_HTML
    assert "<script>" not in OPERATIONS_CONSOLE_HTML


def test_console_api_adapter_and_dom_rendering_are_fail_closed() -> None:
    assert "/ops/console/snapshot" in OPERATIONS_CONSOLE_JS
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
