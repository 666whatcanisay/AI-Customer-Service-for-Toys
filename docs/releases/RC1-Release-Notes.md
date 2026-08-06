# AI-CS Channel Engine 0.1.0rc1 Release Notes

## 定位

RC1 是 Channel Engine 首个来源冻结候选版本。它收敛现有 Runtime、Adapter、Session、Gateway、Approval、Execution、Receipt、Outbox、Recovery 与 Observability 能力，不增加新的平台能力。

## 冻结内容

- Channel Runtime 生命周期、Heartbeat 与有界恢复。
- Channel Adapter 与多 Session 隔离模型。
- Gateway Client、HMAC、timeout、幂等和 Error Envelope。
- Decision → Human Approval → Execution Lease → Receipt 安全链。
- SQLite 持久化、Execution Ledger 与 transactional Outbox。
- Runtime、Trace、Approval 与 Execution 可观测接口。

## Contract

- Gateway Contract wire version：`1.0`
- Canonical SHA-256：`e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`
- 本 RC 不修改 schema，也不增加 wire 字段。

## 安全状态

- `real_platform_activation_allowed=false`
- `activation_grant_issued=false`
- `real_send_enabled=false`
- `manual_approval=true`
- `auto_reply=false`
- Agent RC 配置默认启用 Kill Switch。

## 兼容性

- Windows
- CPython `3.12.x`
- SQLite
- Gateway Contract V1

## 发布判定

当前工程与测试 Gate 已通过，但 Source Freeze Gate 为 **BLOCKED**：工作树尚未清洁，也没有新的受保护 RC1 commit/tag。因此当前不得发布为 RC1。

最终 READY/BLOCKED 结论以《AI-CS Channel Engine RC1 Release Report V1》和 `release-gate.json` 为准。真实 PDD、真实客户消息、真实发送、自动回复、订单和资金动作均不属于 RC1 发布范围。
