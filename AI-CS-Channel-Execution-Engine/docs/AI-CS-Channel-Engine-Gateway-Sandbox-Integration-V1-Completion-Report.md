# 《AI-CS Channel Engine Gateway Sandbox Integration V1 完成报告》

- 报告版本：V1
- 完成日期：2026-08-04
- Gateway Contract：`1.0`（未修改）
- 最终状态：`CHANNEL_ENGINE_GATEWAY_SANDBOX_INTEGRATION_READY`
- 环境：本机进程内 Mock / SQLite / Fake PDD / Fake Executor
- 安全边界：未连接真实 PDD、未连接真实 AI-CS、未调用真实模型、未发送消息

## 1. 完成结论

Channel Engine 与 AI-CS Gateway Contract V1 的沙盒级闭环已经完成并验证：

```text
Fake PDD Observation
  -> ChannelMessageV1
  -> Conversation Runtime
  -> Sandbox Gateway Client
  -> Mock AI-CS Decision
  -> WAITING_APPROVAL
  -> Human Approval
  -> Execution Ledger / Worker
  -> Fake Execution Adapter
  -> Immutable Receipt
  -> Execution Event
  -> Sandbox Gateway Artifact Receiver
```

闭环同时形成 `request_id -> decision_id -> execution_id -> receipt_id` 的完整 Trace，并关联最终 `event_id`。Gateway failure 不会创建 Execution；Decision 仍然只是一项建议，执行必须经过显式人工批准。

## 2. 新增模块

### 2.1 Runtime

新增 `src/channel_engine/gateway/sandbox.py`，包含：

- `SandboxGatewayClient`
- `GatewaySandboxRuntime`
- `SandboxGatewayArtifactServer`
- `SandboxGatewayArtifactTransport`
- `ScriptedSandboxGatewayTransport`
- `GatewaySandboxTraceStore`
- Gateway sandbox trace、ack 与 execution outcome 模型

该模块通过 `channel_engine.gateway.sandbox` 显式导入，没有加入冻结 Gateway 根包的 eager import 链，避免 Storage、Gateway、Execution 的初始化循环依赖。

### 2.2 Tests

新增：

```text
tests/contract/test_gateway_sandbox_contract_v1.py
tests/integration/test_gateway_sandbox_integration_v1.py
tests/integration/test_gateway_sandbox_failures_v1.py
```

## 3. Gateway Client 设计

`SandboxGatewayClient` 组合已有 `AICSGatewayClient`，没有重新定义或放宽 Contract V1。

支持：

| 能力 | 实现 |
|---|---|
| Decision Request | 严格 round-trip 校验后交给 `AICSGatewayClient` |
| Decision Response | 校验 Contract version、response identity、schema 与审批约束 |
| Execution Receipt | `PUT /gateway/v1/execution-receipts/{receipt_id}` 沙盒验收 |
| Execution Event | `PUT /gateway/v1/events/{event_id}` 沙盒验收 |
| Health | 复用已有签名 `/gateway/v1/health` Client |
| Trace | 记录请求、决策、审批、执行、回执、事件元数据 |

所有 Decision、Receipt、Event 都使用冻结 Pydantic Contract 模型序列化并再次反序列化。Artifact transport 仅为进程内 Mock，不打开 Socket、不解析真实地址。

## 4. Contract Validation

### 4.1 Version

Gateway Contract V1 的规范字段是 `contract_version`，不是 `schema_version`。本次未向冻结 Schema 添加别名：

- `contract_version="1.0"` 必须存在；
- 使用 `schema_version` 替代时返回 `422 SCHEMA_VALIDATION_FAILED`；
- body、path、header version/identity 必须一致；
- 未知顶层字段 fail-closed。

### 4.2 字段完整性

DecisionRequest、DecisionResponse、ExecutionReceipt 与 Event 都执行严格字段校验。测试证明缺失 `aggregate_id` 的 Event 被拒绝，不进入 Artifact Store。

### 4.3 Error Envelope

沙盒 Artifact Server 的所有非 2xx 响应都使用冻结 `ErrorEnvelope`。已验证：

- schema mismatch：`422 SCHEMA_VALIDATION_FAILED`；
- 同 ID 异内容：`409 IDEMPOTENCY_CONFLICT`；
- authentication、route、method、media type 和 body size 均有 Contract V1 错误映射；
- Client 拒绝非 Contract Error Envelope。

### 4.4 Timeout 与 Network

- Decision timeout 使用现有最多三次、同 body、同 idempotency key 的 bounded retry；
- 全部 timeout 后抛出 `AICSGatewayTimeout`，Trace 标记 `GATEWAY_UNKNOWN`；
- 网络瞬断使用同一逻辑请求恢复，Trace 的 Decision entry 标记 `recovered=true`；
- Artifact transport 无响应时不推断接收结果，返回 unknown/unavailable，不生成新 artifact id。

### 4.5 Idempotency

| Artifact | Idempotency key | Duplicate result |
|---|---|---|
| Decision | `DecisionRequest.idempotency_key` | 返回原 `DecisionResponse` |
| Receipt | `receipt_id` | `202`, `Idempotency-Replayed: true` |
| Event | `event_id` | `202`, `Idempotency-Replayed: true` |
| Execution | `execute-{decision_id}` | 返回原 Execution/Receipt，不再次调用 Adapter |

相同 key/ID 绑定不同 canonical payload 时立即产生幂等冲突。

## 5. Sandbox Decision Flow

### 5.1 Inbound

测试使用 PDD Prototype 的：

- synthetic `PDDMessageEnvelope`；
- VERIFIED synthetic selector token；
- Fake browser/session；
- `FakePDDAdapter`。

它只产生 `ChannelMessageV1`，没有 `send_message` 方法，也没有真实平台连接。

### 5.2 Decision

Conversation Runtime 构建冻结 `DecisionRequest`。Sandbox Client 将请求交给 `MockAICSServer`，返回：

- Contract V1 `DecisionResponse`；
- `requires_approval=true`；
- `metadata.real_ai_cs_called=false`；
- Decision 状态 `WAITING_APPROVAL`。

此时没有 Approval、Execution 或 Receipt，Fake Executor 调用次数为 0。

### 5.3 Approval 与 Execution

只有调用 `GatewaySandboxRuntime.approve(..., approved_by=...)` 后才创建 PENDING Execution。之后必须再次显式调用 `execute_approved(execution_id)`；Worker 仍会原子验证：

- Decision 为 `APPROVED`；
- Approval 为 `APPROVED`；
- Execution 为 `PENDING`；
- Worker lease 有效。

执行目标是 `FakeExecutionAdapter`，结果详情固定证明：

- `real_channel_called=false`；
- `customer_message_sent=false`。

## 6. Receipt 与 Execution Event

Worker 先在 SQLite Ledger 写入不可变 Receipt 与 transactional outbox facts。Sandbox Runtime 再把终态映射成冻结 Gateway artifacts：

- `ExecutionReceipt`
- aggregate 为 `Execution` 的终态 `Event`

Event 类型根据终态映射：

- `SUCCESS -> EXECUTION_SUCCEEDED`
- `FAILED -> EXECUTION_FAILED`
- `UNKNOWN -> EXECUTION_UNKNOWN`

Execution Event ID 由 execution identity 与 terminal event type 确定性生成。重复编排只产生 Artifact replay，不产生新 Receipt、Event identity 或 Adapter 调用。

## 7. Failure Handling Evidence

| 场景 | 结果 | Execution 安全结果 |
|---|---|---|
| Gateway 三次 timeout | Trace `GATEWAY_UNKNOWN` | 不创建 Execution，不调用 Executor |
| Invalid DecisionResponse | `GatewayContractViolation` | 事务回滚，不创建 Execution |
| Duplicate DecisionRequest | 返回原 Decision | 一个 Decision |
| Transient network failure | 同一请求 bounded retry 后恢复 | 仍停在 `WAITING_APPROVAL` |
| Duplicate inbound message | 返回原 intake | Gateway 只计算一次 |
| Duplicate approval | 返回原 Execution | 只有一个 Execution |
| Duplicate execute command | 返回原 Receipt/Event | Fake Executor 只调用一次 |
| Execution UNKNOWN | 一份 UNKNOWN Receipt/Event | 自动重试被禁止，要求人工对账 |

`UNKNOWN` 不被转换为 FAILED，也不被加入新的自动执行尝试。

## 8. Observability

Trace Store 为 append-only、metadata-only，阶段包括：

```text
DECISION_REQUESTED
DECISION_RESOLVED | GATEWAY_UNKNOWN | GATEWAY_FAILED
APPROVAL_RECORDED
EXECUTION_ENQUEUED
EXECUTION_SUCCEEDED | EXECUTION_FAILED | EXECUTION_UNKNOWN
RECEIPT_PUBLISHED
EXECUTION_EVENT_PUBLISHED
```

成功 Trace 包含：

- `request_id`
- `decision_id`
- `execution_id`
- `receipt_id`
- `event_id`
- `correlation_id`
- recovery/error metadata

Trace 不记录客户消息正文、Token、Cookie、HMAC secret 或认证 Header。

## 9. Testing

### 新增测试

```text
python -m pytest \
  tests/contract/test_gateway_sandbox_contract_v1.py \
  tests/integration/test_gateway_sandbox_integration_v1.py \
  tests/integration/test_gateway_sandbox_failures_v1.py -q

10 passed in 0.81s
```

覆盖：

- Decision Request/Response；
- Receipt/Event 202 acceptance；
- Contract version 与字段完整性；
- Error Envelope；
- Decision、Receipt、Event 幂等；
- Fake PDD 完整闭环；
- 人工审批边界；
- timeout、invalid response、network recovery；
- duplicate message/approval/execution；
- UNKNOWN 禁止自动重试；
- 完整 ID trace。

### 相关模块回归

Gateway Contract、Gateway Client、Execution Runtime、PDD Prototype 与新增 Sandbox tests 共 60 项通过。

### 全量回归

```text
python -m pytest -q
352 passed, 1 warning in 24.80s
```

唯一 warning 是既有 Starlette TestClient 对 httpx 集成方式的弃用提示，与本次 Gateway 集成和安全结果无关。

## 10. Quality Gates

| Gate | 状态 | Evidence |
|---|---|---|
| Gateway Client Ready | `GATEWAY_CLIENT_READY` | Decision + Receipt + Event 沙盒客户端 |
| Contract Validation Ready | `GATEWAY_CONTRACT_VALIDATION_READY` | Version、schema、Error Envelope、timeout、idempotency tests |
| Decision Flow Ready | `GATEWAY_DECISION_FLOW_READY` | Fake PDD 到 WAITING_APPROVAL 与显式批准执行闭环 |
| Failure Handling Ready | `GATEWAY_FAILURE_HANDLING_READY` | timeout/invalid/network/duplicate/UNKNOWN tests |
| Sandbox Integration Complete | `CHANNEL_ENGINE_GATEWAY_SANDBOX_INTEGRATION_READY` | 10 个新增测试与 352 个全量测试通过 |

## 11. 风险与下一阶段建议

当前仍是 Foundation/Sandbox，不具备生产连接资格：

1. Artifact 发布当前是同步沙盒证明；生产客户端必须由 durable outbox publisher 驱动；
2. Trace Store 当前为进程内 append-only store；生产需要持久化与受控保留策略；
3. Mock AI-CS 只生成确定性合成 Decision，不验证真实模型、RAG 或服务容量；
4. Fake PDD 只使用合成消息，不证明真实渠道协议、会话或消息 ID 稳定性；
5. Artifact transport failure 的真实网络对账和 replay 运维流程尚未验证；
6. 真实环境启用前仍需 credential provider、network allowlist、kill switch 与 operator runbook 联合验证。

建议下一阶段把 `SandboxGatewayClient` 的 Event/Receipt publication port 接到现有 durable outbox publisher，并为 Trace 增加 SQLite 持久化；仍使用 Mock AI-CS 和 Fake PDD 完成 restart recovery 演练，不进入真实渠道或真实模型。

---

Final Status: `CHANNEL_ENGINE_GATEWAY_SANDBOX_INTEGRATION_READY`
