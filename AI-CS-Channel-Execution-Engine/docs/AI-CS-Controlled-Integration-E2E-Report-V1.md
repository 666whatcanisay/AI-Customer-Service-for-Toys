# 《AI-CS Controlled Integration E2E Report V1》

## 1. 结论

Channel Engine 已在受控本地环境中，通过 HTTP 与同级 AI-CS 工程的真实 Gateway Server 实现完成完整协作验证。AI-CS 使用真实的 FastAPI Gateway 路由、HMAC 认证、Schema 校验、Decision 映射和 SQLite 幂等状态库；模型/RAG 外部能力仅由确定性测试 Stub 提供。执行端始终使用 `FakeExecutionAdapter`，没有连接真实渠道、没有浏览器自动化、没有自动发送。

最终状态：`CHANNEL_ENGINE_CONTROLLED_AI_CS_INTEGRATION_COMPLETE`

## 2. 验证边界

本次允许且实际执行：

- Channel Engine 新增真实 AI-CS 兼容 scope 与受控集成测试。
- Health 从 `GET /health` 切换到 `GET /gateway/v1/health`。
- Health 和 Decision 均执行 Gateway V1 HMAC-SHA256 签名。
- 通过 loopback HTTP 启动同级 AI-CS 源码中的真实 Gateway Server。
- 保存去除签名值后的 Request、Response、Decision、Approval、Execution、Receipt、Event 证据。

本次没有执行：

- 没有修改 AI-CS 工程、RAG、Prompt、模型或业务逻辑。
- 没有修改 Gateway Contract V1 或 JSON Schema。
- 没有连接生产 AI-CS、真实拼多多或其他真实平台。
- 没有真实发送、资金操作或浏览器自动化。

## 3. 受控拓扑

```text
FakePDDAdapter
  -> ConversationService
  -> ProductionGatewayClient
  -> HTTP loopback
  -> AI-CS POST /gateway/v1/decisions
  -> DecisionResponse V1
  -> Human Approval
  -> ExecutionWorker
  -> FakeExecutionAdapter
  -> immutable Receipt
  -> transactional Outbox
  -> FakeEventPublisher
```

AI-CS 测试进程直接导入同级 `AI-CS/backend/app` 的 `create_app` 和 Gateway 模块。测试替换的只有 RAG 边界能力，Gateway 的路由、认证、契约解析、错误映射和幂等存储均为真实实现。AI-CS 状态库和日志仅写入 pytest 临时目录。

## 4. Health Integration

Health Client 现使用：

- 方法与路径：`GET /gateway/v1/health`
- 请求正文：空字节 `b""`
- 内容哈希：`SHA-256(b"")`
- 认证：`HMAC-SHA256`
- 强制元数据：contract version、timestamp、nonce、content hash、request ID、correlation ID、idempotency key
- 响应校验：HTTP 200、Contract 版本、request/correlation 回显、Health Schema、gateway/capability version

实际结果：

| 检查项 | 实际值 | 结果 |
|---|---|---|
| 匿名 Health | `401 AUTHENTICATION_REQUIRED` | 通过 |
| 签名 Health | `200 HEALTHY` | 通过 |
| Service | `ai-cs-gateway` | 通过 |
| Contract | `1.0` | 通过 |
| Gateway version | `ai-cs-gateway.v1` | 通过 |
| Capability version | `decision.ai-cs-scope.v1` | 通过 |
| Real AI-CS connected | `true` | 通过 |
| Production channel connected | `false` | 通过 |

## 5. Real Decision Flow

Channel Engine 新增 `AICSScope` 兼容模型，并通过 `ConversationService.decision_context_provider` 注入 AI-CS 要求的 `context.ai_cs_scope`：

```json
{
  "tenant_id": "TENANT-SYNTHETIC",
  "platform": "pdd",
  "store_code": "STORE-SYNTHETIC",
  "product_id": "PRODUCT-SYNTHETIC",
  "sku_id": null
}
```

真实 AI-CS 返回字段与 Gateway V1 的对应关系：

| 目标语义 | Gateway V1 位置 | 实际结果 |
|---|---|---|
| `decision_id` | `decision_id` | `decision-*`，通过 |
| `reply_draft` | `proposed_content` | 有非空草稿，通过 |
| `risk_level` | `metadata.risk_level` | `LOW`，通过 |
| Gateway action | `action` | `SUGGEST_REPLY`，通过 |
| AI-CS action | `metadata.ai_cs_action` | `CONTROLLED_ANSWER`，通过 |
| `requires_approval` | `requires_approval` | `true`，通过 |

说明：冻结的 Gateway Contract V1 将回复草稿命名为 `proposed_content`，因此报告和证据中的 `reply_draft` 是对该字段的业务语义别名，没有更改 Contract。

## 6. 成功链路 Timeline

| 顺序 | 实体/动作 | 状态或事件 | 关键证据 |
|---:|---|---|---|
| 1 | Fake Channel | Message 接收 | `MESSAGE_RECEIVED` |
| 2 | Message | `RECEIVED -> PROCESSING` | Conversation transaction |
| 3 | AI-CS Request | 已签名 `POST /gateway/v1/decisions` | HTTP 200，非 replay |
| 4 | Decision | `CREATED -> WAITING_APPROVAL` | `DECISION_CREATED`, `DECISION_WAITING_APPROVAL` |
| 5 | Message | `COMPLETED` | `MESSAGE_COMPLETED` |
| 6 | Human Approval | `APPROVED` | `DECISION_APPROVED` |
| 7 | Execution | `PENDING -> RUNNING -> SUCCESS` | `EXECUTION_STARTED`, `EXECUTION_SUCCEEDED` |
| 8 | Receipt | `SUCCESS` | `RECEIPT_RECORDED` |
| 9 | Outbox | 8 个事件全部 `PUBLISHED` | `FakeEventPublisher` |

执行隔离断言：

- `FakeExecutionAdapter.call_count == 1`
- Receipt `real_channel_called == false`
- Receipt `customer_message_sent == false`
- `FakePDDAdapter.send_call_count == 0`

## 7. Failure Tests

| 场景 | 注入方式 | 预期/实际结果 | 执行隔离 |
|---|---|---|---|
| AI-CS timeout | 真实 Gateway 调用的受控 Provider 延迟超过 HTTP timeout | `AICSGatewayTimeout`；Engine 事务回滚 | 无 Execution、无 Receipt、无发送 |
| Invalid signature | 使用错误 HMAC secret | `401 AUTHENTICATION_FAILED`，非重试错误 | 不进入业务执行 |
| Schema mismatch | 缺少 `context.ai_cs_scope` | `422 SCHEMA_VALIDATION_FAILED`，field=`context.ai_cs_scope` | 不进入业务执行 |
| Duplicate request | 两个独立 Client 发送相同 idempotency key 与 payload | 响应完全相同；第二次 `Idempotency-Replayed: true` | AI-CS 复用已存 Decision |
| UNKNOWN state | Fake Executor 模拟网络结果不确定 | Execution=`UNKNOWN`、Receipt=`UNKNOWN`、attempt=1 | Worker 不自动重试，要求人工对账 |

Timeout 场景使用单次传输尝试，使验证确定且不会在测试中制造额外未决请求；运行时的 Gateway Retry Policy 仍保持 Contract V1 的 1–3 次可配置边界。

## 8. Evidence

机器可读证据：[`evidence/AI-CS-Controlled-Integration-E2E-Evidence-V1.json`](../evidence/AI-CS-Controlled-Integration-E2E-Evidence-V1.json)

证据包含：

- 签名已脱敏的 Decision Request headers 与完整 body
- Decision Response status、headers 与目标字段映射
- 持久化 Decision、Approval、Execution、Receipt
- 8 个领域 Event
- Outbox 发布计数和 Fake Publisher 隔离标记

任何 HMAC signature、secret、真实客户数据、真实平台标识均未写入证据。

## 9. Contract 无漂移证明

| 冻结资产 | SHA-256 |
|---|---|
| `src/channel_engine/gateway/contract.py` | `6E08DE8085B1C217EC16C6BFE1AA03E2951BBD507A4EE0B2552F6FA1C18D0F06` |
| `schemas/ai-cs-channel-engine-gateway-contract-v1.schema.json` | `B2DC7467B14FAAB4D976BB655EF260FE352267E95DD4757BF10035C97CFC5D75` |

本次变更没有触碰上述两个资产。Contract 专项测试：`8 passed`。

本次运行所读取的 AI-CS Gateway 源文件 SHA-256：

| AI-CS 源文件 | SHA-256 |
|---|---|
| `backend/app/gateway/auth.py` | `C49D83E43BE4CAFAF5371DA97C966EB05417CE82EE953D6F3E67294B4C29CDD3` |
| `backend/app/gateway/contract.py` | `267E262DA4CD44B5D1A212B100B8B71D7F1540FDC624558BEC80F7953378EB40` |
| `backend/app/gateway/routes.py` | `4CE4357010896A7ED44075A3ECF90764A7B04674A306A2711187E041A57B963D` |
| `backend/app/gateway/service.py` | `559D35E81550A917DCB25E116DEE9BBB7814CAFE888E0575B576960C97F489B6` |
| `backend/app/gateway/store.py` | `5E17AC0BA8B354E43AABF81F31C94FBEB77AD351FFBDBE0649A09DD6717462F5` |

这些文件只读使用，未由本任务修改。

## 10. 测试结果与 Quality Gates

执行日期：2026-08-04（Asia/Shanghai）

| Gate | 验证 | 结果 |
|---|---|---|
| Gate 1 | 签名 Health + 完整真实 Decision 链路 | PASS |
| Gate 2 | AI-CS Response 字段与 Contract 映射 | PASS |
| Gate 3 | Human Approval + Fake Execution 隔离 | PASS |
| Gate 4 | timeout/signature/schema/duplicate/UNKNOWN | PASS |
| Gate 5 | Request/Response/实体/Receipt/Event 证据 | PASS |
| Gate 6 | Gateway Contract V1 无漂移 | PASS |

测试命令与结果：

```text
.venv\Scripts\python.exe -m pytest tests\e2e\test_controlled_ai_cs_integration.py -q
6 passed

.venv\Scripts\python.exe -m pytest tests\contract\test_gateway_contract_v1.py -q
8 passed

.venv\Scripts\python.exe -m pytest -q
111 passed, 1 warning
```

唯一 warning 是 FastAPI TestClient 关于未来 `httpx2` 的上游弃用提示，不影响本次 Gateway 功能或结果。

## 11. Final Status

`CHANNEL_ENGINE_CONTROLLED_AI_CS_INTEGRATION_COMPLETE`
