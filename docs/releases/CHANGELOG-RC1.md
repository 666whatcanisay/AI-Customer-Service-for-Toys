# Channel Engine Changelog — 0.1.0rc1

## Release preparation

- 将 Channel Engine 版本标识统一为 `0.1.0rc1`。
- 增加 Windows / CPython 3.12 的精确依赖锁 `requirements-rc1.lock`。
- 增加只读 RC1 Gate 验证器和 Release Lock 测试。
- 增加 Release Checklist、Release Notes、Deployment Guide 与 Rollback Guide。
- 修复 README 的编码损坏并明确 RC 安全边界。

## Frozen existing capabilities

- Runtime lifecycle、Heartbeat、Recovery 与 Health。
- Adapter、Session、Cursor/ACK 与 Credential Reference。
- Gateway Contract V1、HMAC、idempotency、timeout 与 fail-closed error handling。
- Approval、Lease、Execution、Receipt、Ledger 与 Outbox。
- Control Plane、Kill Switch、Audit、Trace 与 Operations API。

## Security posture

- 真实平台 activation、grant 和 send 标志继续固定为 `false`。
- 未审批 Execution 继续被拒绝。
- `UNKNOWN` 继续禁止自动重试。
- 未引入 Cookie、Token 或密码明文配置。

## Not included

- 真实 PDD 连接或登录。
- 真实客户消息读取或发送。
- 自动回复、退款、订单修改或资金动作。
- Gateway Contract 变更。
- AI-CS 业务逻辑变更。
