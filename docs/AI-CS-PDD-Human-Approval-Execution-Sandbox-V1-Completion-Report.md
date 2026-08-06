# 《AI-CS PDD Human Approval Execution Sandbox V1 完成报告》

## 技术摘要

`PDD_HUMAN_APPROVAL_EXECUTION_SANDBOX_READY` 已达到：一条停留在 `WAITING_APPROVAL` 的合成 PDD Decision，只有在操作员显式批准后，才会创建唯一 Approval 和 Execution；Worker 必须领取有效 Lease，执行边界再签发并验证 Ledger Authorization，随后才允许 `FakePDDExecutor` 模拟发送并追加不可变 Receipt、Audit Event 与 Outbox 记录。

本次实现没有连接 PDD、没有读取真实客户消息、没有真实发送、没有自动批准或自动回复，也没有退款、订单或资金操作。`FakePDDExecutor.send_message()` 虽用于模拟执行接口，但其输出恒定证明 `customer_message_sent=false`，真实平台调用计数恒为 0。

验证结果：新增专项测试 **10 passed**，PDD 相关回归 **157 passed**，全仓回归 **452 passed**，失败数均为 0。唯一 warning 是既有 FastAPI `TestClient` 弃用提示，与本次变更无关。

## 1. Runtime 架构

```text
Synthetic PDD Message
  -> AI-CS Decision.WAITING_APPROVAL
  -> Operator Approval（显式调用）
  -> Decision.APPROVED + Approval.APPROVED
  -> Execution.PENDING
  -> Worker claim + Execution Lease
  -> Execution.RUNNING
  -> Ledger Authorization（Approval/Lease/内容绑定）
  -> FakePDDExecutor
  -> Execution SUCCESS | FAILED | UNKNOWN
  -> Immutable Receipt
  -> Event + Transactional Outbox
```

新的 Sandbox Orchestrator 位于 Execution 层，而不是只读 `pdd_adapter` Prototype 包。这样既能复用现有 Approval、Lease、Worker、Ledger、Receipt 和 Outbox，也能继续保证观察层公共接口没有 `send` 或 `execute` 能力。

| 组件 | 职责 | 安全边界 |
|---|---|---|
| `PDDHumanApprovalExecutionSandbox` | 显式批准、执行单个已批准任务、回放终态 Receipt、生成 Trace | 不扫描队列、不自动批准、不自动重试 |
| `ExecutionCoordinator` | 将 `WAITING_APPROVAL` 原子转换为 Approval + PENDING Execution | 重复同一操作员批准返回原记录 |
| `ExecutionQueue` / `ExecutionWorker` | 精确领取 Execution、持有和续租 Lease、落终态 | 无有效审批无法领取；同一任务不能被多个 Worker 同时执行 |
| `LedgerExecutionAuthorizationService` | 将 Decision、Approval、Execution、Lease、操作员与内容绑定为授权能力 | 任一标识、内容、租约或状态不匹配即拒绝 |
| `FakePDDExecutor` | 模拟 SUCCESS、FAILED、UNKNOWN | 无网络 Transport；真实发送计数固定为 0 |
| Receipt / Event / Outbox | 保存执行结果及审计证据 | Receipt 冻结且每个 Execution 只能追加一次 |

## 2. 人工批准工作流

`approve(decision_id, operator=...)` 是唯一批准入口。它复用现有 `ExecutionCoordinator.approve_and_enqueue()`，完成以下原子状态变化：

1. Decision 必须处于 `WAITING_APPROVAL`；
2. 创建 `Approval.APPROVED`，并记录显式操作员；
3. Decision 进入 `APPROVED`；
4. 创建一个 `Execution.PENDING`；
5. 写入 Decision Approved Event 和 Outbox；
6. 同一 Decision、同一操作员重复批准时返回原 Approval 与 Execution。

`execute_decision()` 只解析已经存在的批准结果，不会创建 Approval。Decision 未批准、Approval 不存在或不是 `APPROVED`、Execution 不存在或 Approval 关联不一致时，均以 `PDD_SANDBOX_APPROVAL_REQUIRED` Fail Closed，Adapter、Receipt 与发送计数保持 0。

## 3. Execution Lease 与 Authorization

Worker 使用 `run_execution(execution_id)` 精确领取一个任务，不执行无界队列扫描。领取前数据库会再次验证 Decision 和 Approval 都是 `APPROVED`；领取成功后 Execution 进入 `RUNNING` 并生成 Worker 所有权、Lease Token 与过期时间。

Fake Executor 不能使用裸 `ExecutionCommand` 直接执行。它只接受 Worker 传入的 `ClaimedExecutionContext`，并在模拟发送前完成两层校验：

- Lease 层：Execution 为 `RUNNING`，Worker、Lease Token 与有效期匹配；
- Authorization 层：Decision、Approval、Execution、操作员、操作类型、批准正文和 Idempotency Key 完整匹配。

过期 Lease 用例在授权阶段被拒绝为 `PDD_SANDBOX_AUTHORIZATION_DENIED`，`send_attempt_count=0`、Receipt=0。这样即使直接获得 Fake Executor 对象，也无法绕过 Worker Lease 和批准边界。

## 4. Fake PDD Executor

`FakePDDExecutor` 支持三种确定性模式：

| 模式 | Execution | Receipt | 重试规则 | 真实副作用 |
|---|---|---|---|---|
| `SUCCESS` | `SUCCESS` | `SUCCESS` | 不需要 | 0 |
| `FAILED` | `FAILED` | `FAILED` | 本 Sandbox 不自动重试 | 0 |
| `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | 明确禁止自动重试，要求人工核对 | 0 |

Fake Executor 不包含 HTTP 客户端、Cookie、Token、浏览器写操作或真实 PDD 端点。模拟结果携带 `human_approved=true`、`lease_validated=true`、`authorization_validated=true`，同时固定记录 `real_platform_called=false`、`customer_message_sent=false`、`automatic_reply=false`、`refund_performed=false`、`order_modified=false` 和 `payment_performed=false`。

`send_message()` 只接受 `AuthorizedOutboundMessage`，传入裸字符串或未经授权对象会抛出 `ExecutionBoundaryDenied`。其 Idempotency Key 与批准内容、Decision、Approval、Execution 和操作员指纹绑定；冲突会拒绝而不是覆盖。

## 5. Receipt、Ledger 与 Event

所有实际进入 Adapter 的终态执行都会产生一个 Receipt。Receipt 包含并关联：

- `decision_id`
- `approval_id`
- `execution_id`
- `receipt_id`
- `authorization_id`
- `status`（`SUCCESS`、`FAILED` 或 `UNKNOWN`）
- 人工批准、Lease、Authorization 和零真实发送证明

Receipt 模型使用 frozen 配置，运行时修改会失败；Repository 的 `append_receipt()` 还会拒绝同一 Execution 的第二个 Receipt。因此不可变性同时受到对象模型和持久化层保护。

成功、失败和未知结果分别记录 `EXECUTION_SUCCEEDED`、`EXECUTION_FAILED`、`EXECUTION_UNKNOWN`，所有终态都记录 `RECEIPT_RECORDED`。审批和启动阶段还记录 `DECISION_APPROVED` 与 `EXECUTION_STARTED`，并通过 Transactional Outbox 保存。

## 6. Audit Trace

`PDDApprovalExecutionTrace` 提供一条可核验的标识链：

```text
message_id
  -> decision_id
  -> approval_id
  -> execution_id
  -> receipt_id
  -> authorization_id
```

Trace 同时报告 Decision、Approval、Execution 和 Receipt 状态，并将 `automatic_retry_allowed=false` 与 `customer_message_sent=false` 固定在冻结模型中。Trace 和 Safety Snapshot 不包含客户正文、Cookie、Token、密码、Credential Reference 或真实账号信息。

## 7. 故障与幂等验证

| 场景 | 预期与验证结果 | Adapter 调用 | Receipt |
|---|---|---:|---:|
| Approval 不存在 | `PDD_SANDBOX_APPROVAL_REQUIRED`，执行前停止 | 0 | 0 |
| 重复批准 | 返回原 Approval 与 Execution，数据库各 1 条 | 0 | 0 |
| Lease 过期 | Authorization 拒绝，Fake send 前停止 | 1 次边界检查 / 0 次 send | 0 |
| Execution FAILED | 记录 FAILED Execution、Receipt 与 Event | 1 | 1 |
| Execution UNKNOWN | 记录 UNKNOWN Receipt，第二次请求回放原 Receipt | 总计 1 | 总计 1 |
| 重复终态执行 | 不重新调用 Adapter | 0 次新增 | 返回原 Receipt |

UNKNOWN 的第二次执行请求不会重新领取 Lease，也不会重新调用 Adapter；它直接返回原 Receipt，并标记 `replayed=true`、`adapter_called=false`。该规则避免在“动作可能已触发但结果无法确认”时重复发送。

## 8. 测试结果

| 验证范围 | 通过 | 失败 | Warning | 说明 |
|---|---:|---:|---:|---|
| 人工审批执行专项 | 10 | 0 | 0 | 新增 Unit、Integration、Security 测试 |
| PDD 相关回归 | 157 | 0 | 1 | 嵌套范围；既有 FastAPI TestClient 弃用提示 |
| 全仓回归 | 452 | 0 | 1 | 嵌套范围；warning 与本次变更无关 |

专项覆盖：未批准拒绝、重复批准幂等、租约过期、授权内容绑定、SUCCESS、FAILED、UNKNOWN 不重试、Receipt 不可变、Trace 完整性、Fake Executor 隔离、敏感字段扫描与零真实副作用。

机器可读测试证据位于 `evidence/pdd-human-approval-execution-sandbox-v1/validation-results.json`。三组数字是逐级嵌套的验证范围，不应相加。

## 9. 风险与限制

1. 本状态证明的是 Sandbox 执行安全和持久化语义，不证明真实 PDD Transport、Session 或平台响应语义。
2. 操作员目前由合成 `operator` 字符串表示；生产使用前仍需接入已认证的 Operator Identity、权限范围与不可抵赖审计。
3. `FAILED` 是否允许人工发起新执行、允许几次以及需要何种二次审批，仍需单独冻结策略；本 Sandbox 不自动重试。
4. `UNKNOWN` 已禁止自动重试，但生产环境仍需提供人工核对与 Reconciliation Runbook。
5. 当前测试使用合成 Message 和受控 Gateway，不包含真实客户数据、浏览器会话或 PDD 账户。

## 10. 下一阶段建议

1. 冻结 Operator Authentication / Authorization Contract，禁止仅凭展示名批准。
2. 为 UNKNOWN 建立只读人工核对任务与状态转换规范，仍不提供自动重试。
3. 增加 Worker 崩溃发生在 Adapter 返回前后的故障注入，核对 Lease Recovery 与 Receipt 唯一性。
4. 将 Trace 投影接入现有 Observability Console，默认隐藏正文，仅展示标识、状态与零副作用证明。
5. 只有在独立的真实渠道安全评审通过后，才允许设计 Transport Adapter；不得把本 Sandbox Ready 解释为真实发送授权。

---

Final Status: `PDD_HUMAN_APPROVAL_EXECUTION_SANDBOX_READY`
