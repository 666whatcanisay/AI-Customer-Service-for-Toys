# Channel Engine RC1 Rollback Guide

## 触发条件

- Runtime 无法启动、停止或恢复。
- Gateway Contract SHA 不匹配。
- Health 持续 FAILED/DEGRADED。
- Approval、Lease、Receipt 或 UNKNOWN 规则异常。
- 凭据、RBAC 或安全默认值异常。
- 出现任何非预期真实平台副作用。

## 冻结顺序

1. 启用全局 Kill Switch，阻止新的 Execution。
2. 正常停止 Runtime、Worker、Adapter 与 Session。
3. 保存 Audit、Receipt、Outbox、Execution Ledger 与 Config Snapshot。
4. 隔离 Gateway 和 Channel endpoint。
5. 记录当前版本、commit、合同 SHA、故障时间和操作人。

## 回滚步骤

1. 确认进程已经正常停止。
2. 将当前程序目录标记为 failed RC，禁止覆盖其 evidence。
3. 恢复上一个已验证、受保护的程序归档。
4. 恢复与该版本兼容的配置快照；Credential 仍只使用 reference。
5. 不执行数据库降级或历史删除。若 schema 不兼容，复制数据库后进入人工迁移流程。
6. 在 Kill Switch ENABLED、Mock/Staging 模式下启动旧版本。
7. 验证 `/health`、Runtime 状态、Receipt、Outbox backlog 和合同 SHA。
8. 只有人工复核完成后，才允许恢复非执行型观察能力。

## 数据保护

- Receipt、Audit、Event 与 Execution Ledger 不得删除或覆盖。
- `UNKNOWN` Execution 不得自动重试。
- 未发布 Outbox Event 保留并依赖幂等 publisher 恢复。
- 不导出或复制 Cookie、Token、密码。

## 回滚完成标准

- Runtime 状态可查询。
- Kill Switch ENABLED。
- Gateway、Adapter 和 Session 均处于预期隔离状态。
- 历史 Receipt 与 Audit 可查询。
- 真实平台连接、客户读取和发送均为 0。
