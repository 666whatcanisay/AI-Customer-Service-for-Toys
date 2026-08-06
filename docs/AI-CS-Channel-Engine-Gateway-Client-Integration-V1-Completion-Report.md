# 《AI-CS Channel Engine Gateway Client Integration V1 完成报告》

- 报告版本：V1
- 完成日期：2026-08-05
- 冻结协议：AI-CS Gateway Contract `1.0`（未修改）
- 最终状态：`CHANNEL_ENGINE_AI_CS_GATEWAY_READY`
- 验证环境：进程内 Mock AI-CS Gateway、Fake PDD、Fake Executor
- 安全边界：未连接生产 AI-CS、未连接真实 PDD、未读取真实客户数据、未发送真实消息

## 1. 完成结论

Channel Engine 已具备面向真实 AI-CS Gateway 的客户端基础：生产接口、HTTP Transport 装配入口、冻结 Contract V1 严格校验、基于凭据引用的 HMAC 认证、有限重试、Circuit Breaker、UNKNOWN 安全语义、统一 Trace，以及支持异常注入的进程内 Mock AI-CS Gateway。

本次完成的是“可连接基础”，不是生产连通声明。所有证据均由本地 Mock 生成，未访问真实 AI-CS 或任何渠道。

## 2. 新增与调整模块

### 2.1 Real-ready Gateway 集成层

新增 `src/channel_engine/gateway/integration.py`：

- `GatewayClientInterface`
- `GatewayClient`
- `GatewayServiceIdentity`
- `GatewayTokenProvider`
- `GatewaySigningToken`
- `ProviderBackedGatewayAuthenticator`
- `GatewayCircuitBreaker`
- `GatewayArtifactOutcomeUnknown`
- `MockAICSGateway`
- `MockAICSGatewayTransport`

该模块通过 `channel_engine.gateway.integration` 显式导入，避免扩大 Gateway、Storage、Execution 根包初始化时的循环依赖。

### 2.2 Sandbox Contract Client 兼容增强

调整 `src/channel_engine/gateway/sandbox.py`：

- 增加通用 `publish_event(event)`；
- 保留 `publish_execution_event(event)` 的 Execution aggregate 限制；
- 增加 `send_execution_result(receipt)` 标准接口别名；
- 继续复用冻结的 Event、ExecutionReceipt、ErrorEnvelope 模型和签名头。

### 2.3 新增测试

```text
tests/unit/test_ai_cs_gateway_integration_client.py
tests/contract/test_ai_cs_gateway_integration_v1.py
tests/integration/test_ai_cs_gateway_integration_runtime_v1.py
```

## 3. Gateway Client 设计

`GatewayClient` 是 Transport 与 Credential Provider 均可注入的 Contract V1 客户端，不生成 AI 回复，不拥有模型或 RAG 逻辑。

| 接口 | 输入 | 输出 | 安全约束 |
|---|---|---|---|
| `request_decision()` | `DecisionRequest` | `DecisionResponse` | 冻结 Schema、HMAC、有限重试、审批语义不变 |
| `publish_event()` | `Event` | artifact acknowledgement | 以 `event_id` 幂等，只重放同一 ID |
| `send_execution_result()` | `ExecutionReceipt` | artifact acknowledgement | 以 `receipt_id` 幂等，不创建替代 Receipt |
| `health_check()` | 无 | `GatewayHealth` | Circuit OPEN 时本地 fail-fast，不发网络请求 |

`from_http()` 可装配已有 `HttpGatewayTransport`。HTTP 环境策略继续保持 production default deny；`production_enabled=false` 时在创建 Transport 阶段即拒绝，不触网。

## 4. Contract 兼容性

### 4.1 版本

- Contract 唯一规范版本字段是 `contract_version="1.0"`；
- 不接受 `schema_version` 作为别名；
- Request body、Response body、path identity 与版本响应头必须一致；
- Mock 的 incompatible 模式返回 `2.0`，客户端 fail-closed。

### 4.2 Envelope

- Decision 使用冻结的 `DecisionRequest` / `DecisionResponse`；
- Execution result 使用冻结的 `ExecutionReceipt`；
- Event 使用冻结的 `Event`；
- 非 2xx 必须解析为冻结的 `ErrorEnvelope`；
- 非法签名返回 `401` Contract error，响应不包含 secret material；
- 非法或不完整 payload 不进入业务流。

本次没有修改 Gateway Contract V1 或 AI-CS 核心业务逻辑。

## 5. Authentication

认证边界由三个对象组成：

1. `GatewayServiceIdentity` 只保存 `client_id`、`key_id` 和 `credential_ref`；
2. `GatewayTokenProvider` 根据 opaque reference 获取短期内存凭据；
3. `ProviderBackedGatewayAuthenticator` 每次请求解析凭据并使用现有 Contract V1 HMAC signer 签名。

安全规则：

- `GatewayClient` 与 `from_http()` 均没有 plaintext secret 参数；
- `credential_ref` 拒绝 user-info、query、fragment 及明显的 token/password/cookie/secret 内容；
- Token 必须与 service identity 的 reference 和 key ID 一致且未过期；
- Token 与测试 Provider 的 `repr` 始终显示 `<redacted>`；
- 缺失或错误 reference 在 Transport 前失败，并写入脱敏 Trace；
- `FakeGatewayTokenProvider` 仅供测试，生产 secret backend 不在本阶段实现。

## 6. Retry、Timeout 与 Circuit Breaker

### 6.1 Decision

Decision 复用既有有界重试策略；所有尝试保持相同 request body、`request_id` 和 `idempotency_key`。最终超时抛出 `AICSGatewayTimeout`，不会创建 Decision、Approval 或 Execution。

### 6.2 Event 与 Execution Result

- 只对 retryable error 或 transport acceptance unknown 执行有限重试；
- 每次重试使用同一 `event_id` 或 `receipt_id`；
- 若服务端已受理但响应丢失，第二次请求获得 `replayed=true`，服务端只接受一次；
- 重试耗尽后抛出 `GatewayArtifactOutcomeUnknown`，保留 artifact ID 和尝试次数；
- 不把 unknown 伪装成 SUCCESS，也不创建新 ID。

### 6.3 Circuit Breaker

状态：

```text
CLOSED --failure threshold--> OPEN
OPEN --reset timeout--> HALF_OPEN
HALF_OPEN --success--> CLOSED
HALF_OPEN --failure--> OPEN
```

默认阈值为连续 3 次逻辑调用失败，默认 reset timeout 为 30 秒；参数可配置但均有边界验证。OPEN 状态 fail-fast，避免继续冲击不可用 Gateway。

### 6.4 Execution UNKNOWN

Execution outcome 为 UNKNOWN 时：

- Receipt 必须保持 UNKNOWN 且 `reconciliation_required=true`；
- Event 可以安全发布或幂等重放；
- Execution Adapter 不会自动再次调用；
- 只有人工 reconciliation 后才能采取下一步动作。

## 7. Trace Integration

统一关联：

```text
request_id
  -> decision_id
  -> execution_id
  -> receipt_id
  -> event_id
```

Trace 记录 Gateway 请求、Decision、Approval、Execution、Receipt、Event 的 ID 与状态，不记录 token、secret、cookie 或客户消息正文。当前 Trace Store 为进程内基础实现；生产持久化应由后续 staging 部署接入现有 durable storage/outbox 边界。

## 8. Mock AI-CS Gateway

`MockAICSGateway` 组合已有 Decision Mock Server 与 Artifact Server，覆盖：

- 正常 Decision Response；
- Timeout；
- Contract Error Envelope；
- Invalid Signature；
- Contract version incompatible；
- Event 与 Receipt 接收、幂等 replay 和冲突检测。

Mock Transport 不打开 socket，也不会访问 `.invalid` 或任何外部地址。

## 9. 测试结果

### 9.1 本次新增测试

结果：`14 passed`

覆盖：

- GatewayClient 三个生产接口与签名 health；
- Contract V1 正常、错误、版本不兼容和字段别名拒绝；
- service identity、credential reference、token redaction；
- 缺失凭据在 Transport 前失败；
- timeout、circuit open、half-open recovery；
- artifact timeout 的 UNKNOWN；
- 服务端受理后响应丢失的同 ID replay；
- production default deny 且无网络请求；
- 五类 Trace ID 完整关联；
- Execution UNKNOWN 不自动重试。

### 9.2 Gateway 专项回归

命令覆盖原 Gateway Client、HTTP Adapter、Sandbox Contract、Real Adapter Mock 集成和本次新增测试。

结果：`73 passed in 1.25s`

### 9.3 全量回归

```text
366 passed, 1 warning in 19.72s
```

唯一 warning 来自 FastAPI TestClient 对 Starlette/httpx 兼容层的上游弃用提示，与本次 Gateway 行为无关。

## 10. Quality Gates

| Gate | 证据 | 状态 |
|---|---|---|
| Gateway Client Ready | 三个接口、health、HTTP 装配 | PASS |
| Contract Validation Ready | Version、Request/Response/Error Envelope | PASS |
| Authentication Ready | Service identity、Provider、HMAC、脱敏 | PASS |
| Reliability Ready | Timeout、有限重试、Circuit Breaker、UNKNOWN | PASS |
| Trace Ready | 五类 ID 全链路关联 | PASS |
| Mock Gateway Ready | 正常、超时、错误、版本不兼容 | PASS |
| Regression Ready | Gateway 73/73；全量 366/366 | PASS |

## 11. 剩余风险与约束

1. 尚未与真实 AI-CS Gateway 实例执行握手，真实 TLS、DNS、代理和时钟偏差仍需在受控 staging 验证。
2. 生产 `GatewayTokenProvider` 需要由部署环境接入 secret manager；本阶段只有协议和 Fake Provider。
3. Circuit Breaker 状态是单进程内存状态，多节点共享熔断不在 V1 范围。
4. Trace 当前不是生产审计存储；artifact 的最终可靠投递仍应通过 durable outbox 驱动。
5. Mock 不能替代真实网关的容量、限流、证书轮换和灾难恢复验证。
6. 本状态不授权连接生产 AI-CS、不授权连接 PDD，也不授权任何真实发送。

## 12. 下一阶段建议

下一阶段应在明确批准的本地或 staging AI-CS Gateway 上进行 controlled integration：配置非生产 endpoint 与 secret reference，校验签名 health、Contract 版本和时钟偏差，再用完全 synthetic payload 验证 Decision/Event/Receipt。保持 Fake Channel、Fake Executor、manual approval 和 production default deny，成功前不得扩大到真实 PDD。

## Final Status

`CHANNEL_ENGINE_AI_CS_GATEWAY_READY`
