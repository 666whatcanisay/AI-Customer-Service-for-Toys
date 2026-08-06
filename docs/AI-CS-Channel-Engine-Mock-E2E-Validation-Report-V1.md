# 《AI-CS Channel Engine Mock E2E Validation Report V1》

| 项目 | 结果 |
|---|---|
| Run ID | `MOCK-E2E-2026-08-04-V1` |
| 执行目标 | `AI-CS-Channel-Execution-Engine` |
| 场景 | 完整模拟业务闭环 + 4 个异常场景 |
| E2E 结果 | `5 passed`，`0 failed` |
| 全量结果 | `81 passed`，`0 failed` |
| 总覆盖率 | `91%` |
| Gateway Contract | V1 冻结，无漂移 |
| 真实外部调用 | `0` |
| 最终状态 | `CHANNEL_ENGINE_MOCK_E2E_READY` |

## 1. 验证结论

完整 Mock 闭环通过：

```text
Fake Customer
    -> FakePDDAdapter.receive_message
    -> NormalizedMessage
    -> ConversationService
    -> AICSGatewayClient
    -> MockAICSServer Decision
    -> Human Approval
    -> Execution Queue / Lease
    -> Execution Worker
    -> FakeExecutionAdapter
    -> immutable Receipt
    -> transactional Outbox
    -> FakeEventPublisher
```

成功场景验证了全部要求状态：

- Message：`RECEIVED -> PROCESSING -> COMPLETED`；
- Decision：`CREATED -> WAITING_APPROVAL -> APPROVED`；
- Execution：`PENDING -> RUNNING -> SUCCESS`；
- Receipt：`CREATED`，持久化为唯一且不可变的 `SUCCESS` Receipt；
- Event/Outbox：8 条领域事件、8 条一一对应 Outbox、8 条 Contract V1 Event 全部发布。

“执行发送”由 `FakeExecutionAdapter.execute()` 模拟。其成功表示执行运行时完成了受批准的假执行，不代表客户收到消息；Receipt 明确记录 `real_channel_called=false`、`customer_message_sent=false`。`FakePDDAdapter.send_call_count` 全程为 `0`。

## 2. 测试环境与安全边界

| 组件 | 本次实现 |
|---|---|
| Customer | 测试构造的 `FakePDDInboundMessage` |
| Channel | 纯内存 `FakePDDAdapter` |
| Gateway Client | `AICSGatewayClient` |
| AI-CS | 进程内 `MockAICSServer` |
| Gateway Transport | `MockAICSTransport`，无 socket/HTTP |
| Approval | 显式测试调用，operator=`mock-e2e-human-operator` |
| Execution | 数据库队列、lease、`ExecutionWorker` |
| Execution Adapter | `FakeExecutionAdapter` |
| Database | 每个测试独立 SQLite 临时数据库 |
| Event Publisher | 纯内存、幂等 `FakeEventPublisher` |

禁止边界保持：

1. 未连接真实 AI-CS；
2. 未连接拼多多或其他真实平台；
3. 未使用 Playwright、Selenium 或浏览器自动化；
4. 未自动发送客户消息；
5. 未调用 AI 模型；
6. 未修改 Gateway Contract V1 源码或 schema。

## 3. 成功场景输入

```json
{
  "chat_id": "e2e-success-chat",
  "message_id": "e2e-success-message",
  "buyer_id": "buyer-e2e-success-chat",
  "body": "Please check the delivery status"
}
```

测试生成的 UUID 类实体 ID 在每次运行中不同。以下证据表使用稳定别名；测试实际断言了所有真实 ID、外键和 event/outbox identity 的逐字一致性。

## 4. Timeline

| 顺序 | 动作 | 状态/证据 |
|---:|---|---|
| T00 | Fake Customer 消息入队 | Adapter enqueue=`true` |
| T01 | Adapter 接收并归一化 | channel=`fake-pdd`，receive count=`1` |
| T02 | 创建 Message | `RECEIVED`；`MESSAGE_RECEIVED` |
| T03 | Conversation 开始处理 | Message=`PROCESSING` |
| T04 | Gateway Client 请求 Mock AI-CS | server request=`1`，decision compute=`1` |
| T05 | 创建 Decision | Decision=`CREATED`；`DECISION_CREATED` |
| T06 | 等待人工批准 | Decision=`WAITING_APPROVAL`；Message=`COMPLETED` |
| T07 | 人工批准并入队 | Decision=`APPROVED`；Execution=`PENDING` |
| T08 | Worker 原子领取 lease | Execution=`RUNNING`，attempt=`1` |
| T09 | Fake Execution Adapter 执行 | adapter call=`1`，真实渠道 call=`0` |
| T10 | Worker 完成 | Execution=`SUCCESS`；Receipt=`SUCCESS` |
| T11 | Outbox 发布 | 8/8 `PUBLISHED`，每条 attempt=`1` |

同步事务内短暂的 `PROCESSING` 与 `CREATED` 状态通过测试 spy 包装生产 transition 函数捕获；spy 仍调用原始状态机并验证真实 source/target。最终持久状态与领域事件、Outbox 另行从数据库读取验证。

## 5. Entities

| Alias | 类型 | 关键关系 | 最终状态 |
|---|---|---|---|
| `conversation-1` | Conversation | `(fake-pdd, e2e-success-chat)` | `OPEN` |
| `message-1` | Message | conversation=`conversation-1` | `COMPLETED` |
| `decision-1` | Decision | message=`message-1` | `APPROVED` |
| `approval-1` | Approval | decision=`decision-1` | `APPROVED` |
| `execution-1` | Execution | decision/approval 对应上述实体 | `SUCCESS`，attempt=`1` |
| `receipt-1` | Receipt | execution=`execution-1` | `SUCCESS` |

关系断言：

```text
Conversation.conversation_id == Message.conversation_id
Message.message_id          == Decision.message_id
Decision.decision_id        == Approval.decision_id
Approval.approval_id        == Execution.approval_id
Execution.execution_id      == Receipt.execution_id
```

## 6. State Evidence

| Aggregate | 实际观察序列 | 证据来源 |
|---|---|---|
| Message | `RECEIVED -> PROCESSING -> COMPLETED` | transition spy + final row + message events |
| Decision | `CREATED -> WAITING_APPROVAL -> APPROVED` | transition spy + final row + decision events |
| Execution | `PENDING -> RUNNING -> SUCCESS` | enqueue result + claimed lease + final row |
| Receipt | `CREATED(SUCCESS)` | immutable receipt row + two terminal events |

Worker 完成后再次 `run_once()` 返回 `None`，Fake Execution Adapter call count 保持 `1`，证明队列没有重复任务。

## 7. Receipt Evidence

成功 Receipt 断言：

| 字段 | 验证值 |
|---|---|
| `execution_id` | 等于成功 Execution ID |
| `outcome` | `SUCCESS` |
| `external_reference` | `fake-execution-<execution-id>` |
| `details.mode` | `FAKE` |
| `details.worker_id` | `mock-e2e-success-worker` |
| `details.attempt` | `1` |
| `details.real_channel_called` | `false` |
| `details.customer_message_sent` | `false` |

一致性断言：

- `EXECUTION_SUCCEEDED.payload.receipt_id == Receipt.receipt_id`；
- `RECEIPT_RECORDED.aggregate_id == Receipt.receipt_id`；
- `RECEIPT_RECORDED.payload.execution_id == Receipt.execution_id`；
- 一个 Execution 只有一个 Receipt；重复 Worker run 不产生新 Receipt。

## 8. Event 与 Outbox Evidence

成功场景的领域事件时间线：

| 顺序 | Event Type | Aggregate |
|---:|---|---|
| 1 | `MESSAGE_RECEIVED` | Message |
| 2 | `DECISION_CREATED` | Decision |
| 3 | `DECISION_WAITING_APPROVAL` | Decision |
| 4 | `MESSAGE_COMPLETED` | Message |
| 5 | `DECISION_APPROVED` | Decision |
| 6 | `EXECUTION_STARTED` | Execution |
| 7 | `EXECUTION_SUCCEEDED` | Execution |
| 8 | `RECEIPT_RECORDED` | Receipt |

Event/Outbox 一致性矩阵：

| 检查 | 结果 |
|---|---|
| Event 数量 | `8` |
| Outbox 数量 | `8` |
| 唯一映射 | `outbox_id == "outbox-" + event_id` |
| Topic | 等于 Event Type |
| Payload | 每条均通过冻结 `GatewayEvent` V1 校验 |
| Identity | event ID、aggregate ID、event type、payload 与 Event row 一致 |
| 发布结果 | `8 PUBLISHED` |
| 发布尝试 | 每条 `attempt_count=1` |
| Publisher 幂等键 | `event_id` |

## 9. 异常场景证据

### 9.1 AI Timeout：不执行

| 观察 | 结果 |
|---|---|
| Gateway attempts | `3`，同一业务 body/key |
| Mock timeout count | `3` |
| Client result | `AICSGatewayTimeout(outcome_unknown=true)` |
| Conversation transaction | 回滚 |
| Engine Conversation/Message/Decision | `0` |
| Execution / Receipt / Event / Outbox | `0` |
| Execution Adapter calls | `0` |
| Channel send calls | `0` |

### 9.2 Execution UNKNOWN：不重试

使用 `FakeExecutionAdapter(simulate_network_uncertainty=true)`：

| 观察 | 结果 |
|---|---|
| Adapter calls | `1` |
| Execution | `UNKNOWN`，attempt=`1` |
| Receipt | `UNKNOWN` |
| Gateway Receipt | `reconciliation_required=true` |
| 再次 Worker run | `None` |
| 再次 Adapter call | `0` |
| Terminal Event | `EXECUTION_UNKNOWN` |
| Forbidden Event | 无 `EXECUTION_SUCCEEDED` |
| 自动重试检查 | 抛出 `UnknownExecutionRequiresReconciliation` |

### 9.3 Duplicate Message：幂等恢复

| 观察 | 结果 |
|---|---|
| 首次 Adapter enqueue | `true` |
| 重复 Adapter enqueue | `false` |
| 两次 IntakeResult | 完全相同 |
| Mock AI-CS requests/computes | `1 / 1` |
| Message / Decision | 各 `1` |
| `MESSAGE_RECEIVED` / `DECISION_CREATED` | 各 `1` |
| Event / Outbox | `4 / 4`，无重复 |

### 9.4 Duplicate Approval：禁止重复执行

| 观察 | 结果 |
|---|---|
| 两次 approval result | 完全相同 |
| Approval ID / Execution ID | 分别唯一且稳定 |
| Execution attempt | `1` |
| Execution Adapter calls | `1` |
| Receipt | `1` |
| `DECISION_APPROVED` | `1` |
| `EXECUTION_STARTED` | `1` |
| `EXECUTION_SUCCEEDED` | `1` |
| `RECEIPT_RECORDED` | `1` |

## 10. Gateway Contract 无漂移

任务开始与最终审计的 SHA-256 一致：

| 冻结文件 | SHA-256 |
|---|---|
| `gateway/contract.py` | `6E08DE8085B1C217EC16C6BFE1AA03E2951BBD507A4EE0B2552F6FA1C18D0F06` |
| Gateway Contract V1 schema | `B2DC7467B14FAAB4D976BB655EF260FE352267E95DD4757BF10035C97CFC5D75` |

既有 contract test 同时验证 checked-in JSON Schema 等于 `build_gateway_contract_schema()` 的规范输出。

## 11. 测试结果

验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\e2e\test_mock_e2e_validation.py -q
.\.venv\Scripts\python.exe -m pytest --cov=channel_engine --cov-report=term-missing -q
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

结果：

- Mock E2E：`5 passed`；
- 全量：`81 passed`，`0 failed`；
- 总覆盖率：`91%`；
- Receipt/Event/Outbox consistency：PASS；
- Contract drift：`0`；
- 禁止能力命中：`0`。

测试运行存在一条来自 FastAPI TestClient 依赖层的 `StarletteDeprecationWarning`，不影响 E2E 结果或安全边界。

## 12. Quality Gates

| Gate | 结果 | 证据 |
|---|---|---|
| Gate 1：完整链路通过 | PASS | success E2E、全部状态、8/8 Outbox published |
| Gate 2：异常状态通过 | PASS | Timeout、UNKNOWN、duplicate message/approval |
| Gate 3：Receipt/Event 一致 | PASS | ID/payload/aggregate/outbox 一一对应 |
| Gate 4：Contract 无漂移 | PASS | hash 与 canonical schema test |

最终状态：`CHANNEL_ENGINE_MOCK_E2E_READY`
