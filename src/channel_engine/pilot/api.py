from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from .approval import PilotApprovalError
from .models import (
    PilotDashboard,
    PilotEvidence,
    PilotExecutionResult,
    PilotIntakeResult,
)
from .persistence import PilotPersistenceError
from .runtime import PDDPilotRuntime, PilotRuntimeError
from .live import (
    PilotLiveActivationError,
    PilotLiveActivationService,
    PilotLiveEvidenceReport,
    PilotLivePreflightReport,
)


class PilotApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,159}$",
    )


class PilotKillSwitchRequest(PilotApprovalRequest):
    reason: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_.:-]{2,127}$",
    )


def create_pilot_router(
    runtime: PDDPilotRuntime,
    live: PilotLiveActivationService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/pilot", tags=["pdd-single-store-pilot"])

    @router.get("/status", response_model=PilotDashboard)
    def pilot_status() -> PilotDashboard:
        return runtime.status()

    if live is not None:

        @router.get("/live/preflight", response_model=PilotLivePreflightReport)
        def live_preflight() -> PilotLivePreflightReport:
            return live.preflight()

        @router.post("/live/start", response_model=PilotDashboard)
        def live_start() -> PilotDashboard:
            try:
                return live.start_manual_login()
            except PilotLiveActivationError as exc:
                raise HTTPException(
                    status_code=409,
                    detail={"code": exc.error_code, "message": str(exc)},
                ) from exc

        @router.post("/live/check", response_model=PilotDashboard)
        def live_check() -> PilotDashboard:
            try:
                return live.check_session()
            except PilotLiveActivationError as exc:
                raise HTTPException(
                    status_code=409,
                    detail={"code": exc.error_code, "message": str(exc)},
                ) from exc

        @router.post(
            "/live/messages/poll",
            response_model=PilotIntakeResult | None,
        )
        def live_poll_message() -> PilotIntakeResult | None:
            try:
                return live.poll_one_message()
            except (PilotLiveActivationError, PilotRuntimeError) as exc:
                raise HTTPException(
                    status_code=409,
                    detail={"code": exc.error_code, "message": str(exc)},
                ) from exc

        @router.post(
            "/live/decisions/{decision_id}/approve",
            response_model=PilotExecutionResult,
        )
        def live_approve_decision(
            decision_id: Annotated[str, Path(min_length=1, max_length=128)],
            payload: PilotApprovalRequest,
        ) -> PilotExecutionResult:
            try:
                return live.approve_first_reply(decision_id, payload.operator)
            except (
                PilotLiveActivationError,
                PilotRuntimeError,
                PilotApprovalError,
                PilotPersistenceError,
            ) as exc:
                code = getattr(exc, "error_code", "PILOT_LIVE_APPROVAL_DENIED")
                raise HTTPException(
                    status_code=409,
                    detail={"code": code, "message": str(exc)},
                ) from exc

        @router.post("/live/stop", response_model=PilotDashboard)
        def live_stop() -> PilotDashboard:
            return live.stop()

        @router.get("/live/report", response_model=PilotLiveEvidenceReport)
        def live_report() -> PilotLiveEvidenceReport:
            return live.evidence_report()

    @router.post("/start", response_model=PilotDashboard)
    def pilot_start() -> PilotDashboard:
        return runtime.start()

    @router.post("/check", response_model=PilotDashboard)
    def pilot_check() -> PilotDashboard:
        return runtime.check()

    @router.post("/stop", response_model=PilotDashboard)
    def pilot_stop() -> PilotDashboard:
        return runtime.stop()

    @router.post("/messages/poll", response_model=PilotIntakeResult | None)
    def poll_message() -> PilotIntakeResult | None:
        try:
            return runtime.poll_message()
        except PilotRuntimeError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": exc.error_code, "message": str(exc)},
            ) from exc

    @router.post(
        "/decisions/{decision_id}/approve",
        response_model=PilotExecutionResult,
    )
    def approve_decision(
        decision_id: Annotated[str, Path(min_length=1, max_length=128)],
        payload: PilotApprovalRequest,
    ) -> PilotExecutionResult:
        try:
            return runtime.approve_and_execute(decision_id, payload.operator)
        except (PilotRuntimeError, PilotApprovalError, PilotPersistenceError) as exc:
            code = getattr(exc, "error_code", "PILOT_APPROVAL_DENIED")
            raise HTTPException(
                status_code=409,
                detail={"code": code, "message": str(exc)},
            ) from exc

    @router.post(
        "/executions/{execution_id}/sync",
        response_model=PilotExecutionResult,
    )
    def sync_execution(
        execution_id: Annotated[str, Path(min_length=1, max_length=128)],
    ) -> PilotExecutionResult:
        return runtime.sync_execution(execution_id)

    @router.get("/evidence", response_model=list[PilotEvidence])
    def pilot_evidence(
        limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    ) -> list[PilotEvidence]:
        return runtime.evidence(limit)

    @router.post("/kill-switch/enable", response_model=PilotDashboard)
    def enable_kill_switch(payload: PilotKillSwitchRequest) -> PilotDashboard:
        return runtime.enable_kill_switch(
            operator=payload.operator,
            reason=payload.reason,
        )

    @router.post("/kill-switch/disable", response_model=PilotDashboard)
    def disable_kill_switch(payload: PilotKillSwitchRequest) -> PilotDashboard:
        return runtime.disable_kill_switch(
            operator=payload.operator,
            reason=payload.reason,
        )

    @router.get("/ui", response_class=HTMLResponse)
    def pilot_ui() -> HTMLResponse:
        return HTMLResponse(_PILOT_UI)

    return router


_PILOT_UI = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>PDD Single Store Pilot</title>
  <style>
    :root { font-family: system-ui,sans-serif; color: #182230; background: #f3f5f7; }
    main { max-width: 980px; margin: 38px auto; padding: 0 20px; }
    .banner { background: #fff3cd; border: 1px solid #f4ce71; padding: 14px; border-radius: 10px; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin:18px 0; }
    .card { background:white; border:1px solid #dbe2ea; border-radius:10px; padding:16px; }
    .label { color:#667085; font-size:13px; } .value { font-size:19px; font-weight:650; margin-top:6px; word-break:break-word; }
    .controls { display:flex; flex-wrap:wrap; gap:9px; margin:16px 0; }
    button { border:0; border-radius:8px; padding:10px 15px; color:white; background:#175cd3; cursor:pointer; }
    button.danger { background:#b42318; } button.secondary { background:#475467; }
    input { padding:9px; border:1px solid #cfd8e3; border-radius:7px; }
    #decision { white-space:pre-wrap; background:white; border:1px solid #dbe2ea; border-radius:10px; padding:16px; min-height:60px; }
  </style>
</head>
<body><main>
  <h1>PDD Single Store Pilot</h1>
  <div class="banner">PILOT MODE · auto_reply=false · 所有发送必须由人工点击确认 · 首次激活最多 1 条</div>
  <div class="grid">
    <div class="card"><div class="label">Node</div><div class="value" id="node">-</div></div>
    <div class="card"><div class="label">Store</div><div class="value" id="store">-</div></div>
    <div class="card"><div class="label">Browser</div><div class="value" id="browser">-</div></div>
    <div class="card"><div class="label">Message</div><div class="value" id="message">-</div></div>
    <div class="card"><div class="label">AI</div><div class="value" id="ai">-</div></div>
    <div class="card"><div class="label">Safety</div><div class="value" id="safety">-</div></div>
    <div class="card"><div class="label">Today Send</div><div class="value" id="sendCount">0/1</div></div>
  </div>
  <div class="controls">
    <button onclick="command('start')">启动并打开人工登录</button>
    <button class="secondary" onclick="command('check')">检查登录与店铺</button>
    <button class="secondary" onclick="pollMessage()">读取一条消息</button>
    <button class="danger" onclick="command('stop')">停止</button>
  </div>
  <h2>AI 建议</h2><div id="decision">尚未读取消息</div>
  <div class="controls">
    <input id="operator" value="pilot-operator" aria-label="审批人">
    <button id="approve" onclick="approveDecision()" disabled>人工确认并执行</button>
  </div>
  <p id="notice"></p>
</main><script>
let decisionId = null;
const byId = id => document.getElementById(id);
async function refresh() {
  const data = await (await fetch('/pilot/status')).json();
  byId('node').textContent = data.node;
  byId('store').textContent = data.store_name + ' · ' + data.store_status;
  byId('browser').textContent = data.browser;
  byId('message').textContent = data.message;
  byId('ai').textContent = data.ai;
  byId('safety').textContent = data.safety;
  byId('sendCount').textContent = data.today_send + '/' + data.send_limit;
}
async function command(name) {
  const response = await fetch('/pilot/' + name, {method:'POST'});
  byId('notice').textContent = response.ok ? '完成' : '操作失败'; await refresh();
}
async function pollMessage() {
  const response = await fetch('/pilot/messages/poll', {method:'POST'});
  const data = await response.json();
  if (!response.ok) { byId('notice').textContent = data.detail.code; return; }
  if (!data) { byId('notice').textContent = '暂无消息'; return; }
  decisionId = data.decision_id; byId('decision').textContent = data.answer || 'NO_ACTION';
  byId('approve').disabled = !data.requires_approval; byId('notice').textContent = '等待人工确认';
}
async function approveDecision() {
  if (!decisionId || !confirm('确认由人工批准这条回复并创建唯一 Execution？')) return;
  const response = await fetch('/pilot/decisions/' + decisionId + '/approve', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({operator:byId('operator').value})
  });
  const data = await response.json();
  byId('notice').textContent = response.ok ? ('Execution ' + data.execution_state) : data.detail.code;
  byId('approve').disabled = true; await refresh();
}
refresh();
</script></body></html>"""


__all__ = [
    "PilotApprovalRequest",
    "PilotKillSwitchRequest",
    "create_pilot_router",
]
