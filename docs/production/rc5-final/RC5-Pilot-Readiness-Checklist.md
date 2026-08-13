# RC5 Pilot Readiness Checklist

| 项目 | 状态 | 依据 / 下一步 |
|---|---|---|
| 离线业务链 | PASS | Synthetic/Replay → ExecutionPrepared，黑盒35/35 |
| AI 回复链 | PASS | Context、RAG、Citation、Quality Gate |
| MANUAL_CONFIRM | PASS | Decision → Approval → HUMAN Preparation |
| AUTO_LOW_RISK | PASS | 仅低风险自动准备；真实发送关闭 |
| Execution 安全门 | PASS | 授权、店铺、会话、过期、Kill Switch |
| Windows 部署 | PASS | 隔离安装/升级/卸载/重装 13/13 |
| 版本与 BOM | PASS | `rc5-release-bom.json` |
| Runtime Health | PASS | 最终以 Host、Platform、A/RAG 三份 Activation 与当前 PID/端口/配置一致为准 |
| Source Freeze | PASS | 两仓本地冻结提交、工作区 CLEAN；开发期 DIRTY 不等于运行故障，但 Pilot 前必须清零 |
| Storage Health | PASS | Host、Buffer、Offline Control、Agent Spool 全部 fail-closed 核验 |
| Send Safety | PASS | `real_send_enabled=false`；RealExecutionAttempt/RealSend/RealReceipt 均为0 |
| Pilot Governance Preflight | PASS | 上述技术条件的唯一权威综合判定；不等于已获准操作 PDD |
| 自动化绿色助手 | PASS | 216 tests + typecheck |
| 当前绿色 UI 人工验收 | NOT_VERIFIED | 明早人工执行，不得以自动化替代 |
| 专属 PDD 启动入口离线调用链 | PASS | 配置、路由、参数、Mock 通过；今晚未打开 PDD |
| 真实 PDD Adapter | NOT_VERIFIED | 明早扫码后验证 |
| 真实 PDD Read | NOT_VERIFIED | Adapter PASS 后才可 PASS |
| 真实 PDD AI | NOT_VERIFIED | 需手机测试消息 |
| 真实 PDD Confirm | NOT_VERIFIED | 需真实会话、MANUAL_CONFIRM |
| 真实 PDD Send | NOT_VERIFIED | 最后独立 Gate |

## Gate 决策

```text
RC5_OFFLINE_STABILITY_READY = PASS
MORNING_PDD_SCAN_READY = PASS
CURRENT_GREEN_UI_HUMAN_ACCEPTANCE = NOT_VERIFIED
RC5_FINAL_READY = BLOCKED
AI_CS_PRODUCTION_READY = BLOCKED
```

`MORNING_PDD_SCAN_READY=PASS` 仅表示明早可由用户人工触发专属 PDD Edge 并扫码，不表示今晚访问过 PDD，也不表示真实读取已通过。

`may_enter_read_only_pilot=true` 仅代表技术预检具备条件。实际操作 PDD 仍要求 `CURRENT_GREEN_UI_HUMAN_ACCEPTANCE=PASS`、用户当次人工触发和 `real_send_enabled=false`；目前不得由程序自动开始真实 PDD。

## 明早升级 RC5_FINAL_READY 的条件

- [ ] 只保留并确认正确的绿色助手窗口。
- [ ] Synthetic/Replay 顾客消息、商品/SKU/订单上下文、AI 回复、风险与依据显示正确。
- [ ] 人工点击确认后，后端出现 Approval 与唯一 ExecutionPrepared。
- [ ] `RealExecutionAttempt=0`、`RealSend=0`、`RealReceipt=0`。
- [ ] Identity、Binding、专属 Profile 与登录状态可恢复。

全部满足后：`CURRENT_GREEN_UI_HUMAN_ACCEPTANCE=PASS`，`RC5_FINAL_READY=PASS`，允许进入 `REAL_PDD_ADAPTER_READY`。
