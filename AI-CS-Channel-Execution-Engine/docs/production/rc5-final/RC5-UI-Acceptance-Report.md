# RC5 UI Acceptance Report

## 当前结论

| 范围 | 状态 |
|---|---|
| 绿色助手组件/自动化 UI | PASS（216 tests + typecheck） |
| Synthetic/Replay 后端确认链 | PASS（Decision → Approval → ExecutionPrepared） |
| 历史 2026-08-12 窗口截图与点击证据 | PASS（历史证据） |
| 当前安装候选、当前绿色窗口人工联合验收 | NOT_VERIFIED |

历史窗口曾完成过人工点击，不等于今晚无损刷新后的当前窗口已经人工验收。无人值守期间没有进行 Windows 自动点击，也没有尝试从多个同名窗口猜测 URL。

明早必须按 `real-pdd/MORNING-PDD-PILOT-RUNBOOK.md` 完成：消息和上下文显示 → AI 回复/风险/依据 → 人工点击确认 → 后端 Approval/ExecutionPrepared → `RealExecutionAttempt=0 / RealSend=0 / RealReceipt=0`。通过后才能把 `CURRENT_GREEN_UI_HUMAN_ACCEPTANCE` 从 `NOT_VERIFIED` 改为 `PASS`。
