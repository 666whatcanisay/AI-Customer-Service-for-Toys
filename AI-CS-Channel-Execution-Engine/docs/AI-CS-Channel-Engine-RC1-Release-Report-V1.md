# AI-CS Channel Engine RC1 Release Report V1

## 技术摘要

Channel Engine 的 RC1 工程准备已经完成，但当前 **不得发布**。版本已统一为 `0.1.0rc1`，依赖锁、发布文档、Runtime 专项、Gateway Contract 冻结、安全门禁和 508 项全量回归均通过；RC Gate 共 7 PASS、1 BLOCKED。

唯一 blocker 是 `SOURCE-001`：当前 `main` 工作树仍有 26 个 tracked modification、201 个 untracked entry，且没有新的受保护 RC1 commit/tag。测试通过可以证明行为稳定，却不能证明将要发布的源码范围。因此本次 RC Decision 为 **BLOCKED**，目标状态 `CHANNEL_ENGINE_RC1_READY` 尚未达成。

**Current Status: `CHANNEL_ENGINE_RC1_BLOCKED`**

## 1. Release 判定口径

RC1 READY 要求版本、依赖、文档、Runtime、Contract、安全和测试全部通过，同时源码必须处于可引用、可复现、受保护的干净提交。测试集合存在包含关系，508 是全量 pytest 的唯一总体口径；123、17、17 和 5 是专项子集，不能相加为唯一测试总数。

本报告验证的源码工作区基于 commit `b2c64d54987f1f066a02de8e9e667d5cc0f9857c`，但其后存在大量未提交资产。所有 Release Gate 均为只读审计；本任务没有擅自 stage、commit、tag、删除或重写既有资产。

## 2. Repository Release Audit

| 检查 | 结果 | 证据 |
|---|---|---|
| 版本一致性 | PASS | pyproject、package 与 FastAPI 均为 `0.1.0rc1` |
| 依赖锁 | PASS | 6 个直接依赖；27 个 Windows/Python 3.12 精确锁定分发包 |
| 文档完整性 | PASS | Checklist、Notes、Changelog、Deployment、Rollback 全部存在 |
| Source Freeze | BLOCKED | 26 tracked changes、201 untracked entries、0 staged |

README 的既有编码损坏已修复，安全边界和 RC 安装流程已改为可读中文。`requirements-rc1.lock` SHA-256 为 `21688dcc6496b2cc1f60361510d3fb8a1233513ceaa3622e7cfbe790aad523ff`，`pip check` 无 broken requirement。

## 3. Runtime Release Verification

Runtime 专项 17/17 通过，覆盖：

- START/STATUS/STOP 生命周期。
- Heartbeat 与聚合 Health。
- Browser 故障进入 DEGRADED。
- 有界 Recovery 返回 RUNNING。
- 恢复预算耗尽进入人工干预。
- RUNNING Execution 重启后进入 UNKNOWN，禁止自动重发。
- Outbox 未发布事件恢复和重复发布保护。
- Config 与 Kill Switch 跨重启恢复。

API 级验证确认 `/health`、`/runtime/v1/status`、start、heartbeat、recover 和 stop 均满足预期；执行路径继续要求 Approval 和 Receipt，UNKNOWN auto retry 为 false。

## 4. Gateway Contract Release Lock

Gateway Contract wire version 保持 `1.0`。Canonical SHA-256 仍为：

`e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`

Channel Engine 与 AI-CS 两仓 schema 原始文件再次逐字节比较，结果 IDENTICAL。Cross Repository Integration Test 被包含在最终全量回归中并通过。本任务没有修改 schema 或增加字段。

## 5. Security Release Audit

安全门禁全部通过：

- Credential Provider 保持 reference-only。
- RBAC 固定为 Operator、Supervisor、Admin。
- 未审批 Decision 禁止 Execution。
- Lease 和 Receipt 继续作为执行前后边界。
- `UNKNOWN` 禁止自动重试。
- `real_platform_activation_allowed=false`。
- `activation_grant_issued=false`。
- `real_send_enabled=false`。
- Agent RC 默认 `kill_switch=true`、`manual_approval=true`、`auto_reply=false`。

Security suite 为 17 passed；发布文档和 evidence 的敏感材料扫描为 0 violation。真实 PDD 连接、客户消息读取、发送和 Execution 副作用均为 0。

## 6. Test Freeze

| 测试集 | 结果 |
|---|---|
| Full pytest | 508 passed，0 failed，1 warning |
| Gateway Contract | 123 passed，0 failed |
| Security | 17 passed，0 failed |
| Runtime Release | 17 passed，0 failed |
| RC1 Release Lock | 5 passed，0 failed |
| compileall | PASS |
| pip check | PASS |

唯一 warning 是既有 Starlette TestClient/httpx 弃用提示，不影响 RC 行为结论，但应在后续依赖升级窗口处理。

## 7. Release Artifacts

已生成：

- `docs/releases/RC1-Release-Checklist.md`
- `docs/releases/RC1-Release-Notes.md`
- `docs/releases/CHANGELOG-RC1.md`
- `docs/releases/RC1-Deployment-Guide.md`
- `docs/releases/RC1-Rollback-Guide.md`
- `requirements-rc1.lock`
- `scripts/verify_channel_engine_rc1.py`

部署指南强制 loopback、Mock/Staging、安全默认值与 credential reference；回滚指南要求先 Kill Switch，再停止 Runtime/Adapter，保留 Audit、Receipt、Outbox 和 Ledger，禁止删除历史或自动重试 UNKNOWN。

## 8. 方法与证据

Release Gate 验证器直接读取 pyproject、package version、FastAPI version、依赖锁、发布文档、冻结 schema、Pydantic 安全模型、RBAC、Credential Provider、最终回归证据和 Git porcelain 状态。任何 BLOCKED 项都会返回非零退出码；当前退出码为 2。

核心 evidence：

- `evidence/channel-engine-rc1/release-gate.json`
- `evidence/channel-engine-rc1/regression-results.json`
- `evidence/channel-engine-rc1/security-audit.json`

## 9. 限制与稳健性

验证发生在本地 Windows/Python 3.12 环境，不覆盖生产部署、真实 PDD、真实客户、TLS/代理、长时 soak 或多节点。依赖锁记录的是当前 Windows 验证环境，不是跨平台 universal lock。

最关键的不确定性不是 Runtime 行为，而是 dirty workspace 中哪些资产应进入正式 RC1。若未经审查直接全量提交，可能把 Fake、Sandbox、Discovery、Evidence 或实验产物错误纳入发布基线；若只提交部分文件，又可能遗漏被测试依赖。因此该步骤需要明确的 source allowlist 与人工确认。

## 10. 达到 READY 的唯一剩余路径

1. 按既有 Source Baseline allowlist 审查 26 个 tracked modification 与 201 个 untracked entry。
2. 明确 Production Candidate、Test Only、Deferred 与 Experimental 的提交范围。
3. 创建新的受保护 RC1 commit，并在该提交上创建 RC1 tag。
4. 在干净工作树重新运行 Full、Contract、Security、compileall 与 RC Gate。
5. 只有 `release-gate.json` 返回 `READY`，才将状态更新为 `CHANNEL_ENGINE_RC1_READY`。

## 11. 待确认问题

需要 Release Owner 确认：是否按现有 Source Baseline allowlist 创建新的 RC1 source commit，以及 Evidence/HTML/实验 PDD 资产是否留在仓库但排除出发布包。这个选择会改变正式提交范围，因此不能由本任务擅自推断。

---

RC Decision: `BLOCKED`

Current Status: `CHANNEL_ENGINE_RC1_BLOCKED`

Target Status Not Yet Reached: `CHANNEL_ENGINE_RC1_READY`
