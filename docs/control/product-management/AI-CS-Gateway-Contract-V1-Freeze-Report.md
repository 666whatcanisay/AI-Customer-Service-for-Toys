# 《AI-CS Gateway Contract V1 Freeze Report》

## 1. 执行摘要

AI-CS Server 与 Channel Agent 的 Production Gateway Contract 已冻结为 wire `1.0`。双方现在使用同一 Schema、同一字段语义、同一 HMAC 签名规则、同一错误结构和相容的幂等/重试规则。

Production V1 仅包含：

- `POST /gateway/v1/decisions`
- `GET /gateway/v1/health`

Execution Receipt Server 接口、Event 同步、Agent 注册、多租户和多实例调度均明确延后。冻结不启用真实连接，不部署 Gateway，不接入 PDD，也不授权自动执行。

最终结论：`GATEWAY_CONTRACT_V1_PRODUCTION_FROZEN`。

## 2. 审计基线

| 仓库 | Branch | HEAD | 实际状态 | 本次定位 |
| --- | --- | --- | --- | --- |
| AI-CS | `release/product-reliability-hardening-v1` | `0b3367f85999f1dc840accf23742c290eb53746b` | dirty；Gateway 为 T2 候选资产，尚未形成独立提交 | Server Contract Owner |
| Channel Engine | `main` | `b2c64d54987f1f066a02de8e9e667d5cc0f9857c` | dirty；Agent/Gateway 为 T3 候选资产，尚未形成独立提交 | Agent Contract Consumer |

“Production Frozen”表示通信语义与 Schema 已冻结并通过双方测试，不表示两份 dirty 候选源码已经发布或部署。后续 Release Gate 仍需分别形成可追溯的受控提交。

## 3. Contract Inventory

### 3.1 AI-CS Server 已有候选能力

| 能力 | 代码证据 | 审计结论 |
| --- | --- | --- |
| Decision Request/Response | `backend/app/gateway/contract.py` | 已实现候选；strict Pydantic contract |
| Decision API | `backend/app/gateway/router.py`、`backend/app/gateway/service.py` | 已实现候选；仅做 Gateway 到既有 AI answer service 的边界映射 |
| Health | `backend/app/gateway/router.py`、`backend/app/gateway/service.py` | 已实现候选；需要与 Agent 统一字段 |
| ErrorEnvelope | `backend/app/gateway/contract.py` | 已实现候选；需要统一错误判别字段 |
| HMAC 验证 | `backend/app/gateway/auth.py` | 已实现候选；timestamp、nonce、body hash、constant-time compare |
| 幂等存储 | `backend/app/gateway/store.py` | 已实现候选；completed Decision 7 天，same-key conflict fail closed |

### 3.2 Channel Agent 已有候选能力

| 能力 | 代码证据 | 审计结论 |
| --- | --- | --- |
| Request/Response 模型 | `src/channel_engine/gateway/contract.py` | 已实现候选；原 Schema 与 Server 有差异 |
| HTTP Client | `src/channel_engine/gateway/client.py`、`http.py` | 已实现候选；最多三次传输重试 |
| HMAC Signer/Verifier | `src/channel_engine/gateway/auth.py` | 已实现候选；canonical string 与 Server 一致 |
| Retry/Idempotency | `src/channel_engine/gateway/client.py` | 已实现候选；重试保持 request/body/key，更新 nonce/signature |
| Fake/Mock | `src/channel_engine/gateway/fake.py`、`mock_server.py` | 测试支持，不是生产 Server |
| Receipt/Event domain | `src/channel_engine/gateway/contract.py` | Agent 内部/Deferred；不得进入 Production V1 wire Schema |

### 3.3 审计发现并已关闭的差异

| 差异 | 冻结前 | Production V1 决议 |
| --- | --- | --- |
| 风险字段 | 仅藏在 `metadata.risk_level` | 必填顶层 `risk_level`：`LOW/MEDIUM/HIGH` |
| Health 字段 | Server/Agent 使用不同命名 | 统一 `status/version/capabilities/timestamp`，并保留服务与可达性字段 |
| Error 判别字段 | wire 使用 `code` | 统一序列化为 `error_code`；内部只保留读取兼容别名 |
| Schema 内容 | Agent 包含 Receipt/Event，缺少 Health | Production Schema 仅含 Decision、Health、Error、Auth；Receipt/Event 移出 V1 |
| 规范文档 | Agent Foundation 文档把 Receipt/Event 写成 V1 路由 | 原文档已标记 superseded，双方签入同一 Production 规范 |

## 4. 冻结接口

### 4.1 Version

- Wire contract：`1.0`
- Major path：`/gateway/v1`
- Schema ID：`urn:ai-cs:channel-engine:gateway-contract:v1`
- Canonical Schema SHA-256：`e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`

### 4.2 DecisionRequest

必填字段：

`contract_version`、`request_id`、`idempotency_key`、`correlation_id`、`conversation_id`、`message_id`、`customer_message`、`requested_at`。

`context` 为显式扩展容器。AI-CS 生产 profile 使用 `context.ai_cs_scope` 传递 tenant、platform、store、product 和可选 SKU 上下文；Server 不回退到无 scope 的旧消息路径。

### 4.3 DecisionResponse

必填字段：

`contract_version`、`request_id`、`idempotency_key`、`correlation_id`、`decision_id`、`action`、`proposed_content`、`requires_approval`、`risk_level`、`gateway_version`、`metadata`、`decided_at`。

`requires_approval=true` 是不可放宽的 V1 安全闸。`action=NO_ACTION` 时 `proposed_content=null`。

### 4.4 Health

必填字段：

`status`、`service`、`contract_version`、`version`、`capabilities`、`reachable`、`real_ai_cs_connected`、`timestamp`、`details`。

Health 只证明 Gateway 能力状态，不代表 Agent 获得自动执行授权。

### 4.5 ErrorEnvelope

外层固定为 `contract_version + error`。稳定的机器判别字段为：

`error_code`、`message`、`request_id`、`retryable`、`details`。

同时冻结 `error_id`、`correlation_id`、`retry_after_seconds` 和 `occurred_at`。错误信息禁止包含堆栈、密钥或内部路径。

## 5. Authentication Freeze

认证方式：HMAC-SHA256。请求 headers 必须包含：

- `Authorization`
- `X-AI-CS-Contract-Version`
- `X-AI-CS-Timestamp`
- `X-AI-CS-Nonce`
- `X-AI-CS-Content-SHA256`
- `X-Request-ID`
- `X-Correlation-ID`
- `Idempotency-Key`

Canonical string 使用 UTF-8、单 LF 分隔、末尾无 LF：

```text
HMAC-SHA256
<UPPERCASE_METHOD>
<EXACT_PATH_WITHOUT_QUERY>
<contract_version>
<client_id>
<key_id>
<timestamp_as_sent>
<nonce>
<request_id>
<correlation_id>
<idempotency_key>
<content_sha256>
```

双方已用同一已知向量验证：期望 signature 为 `FYWXv1salDMEWFLncJVmokCssvS0fdTEbhyxOAuC9uc`。该 secret 仅为公开 contract-test 固定值，不是运行凭据。

## 6. Idempotency 与 Retry Freeze

| 场景 | Server 行为 | Agent 行为 |
| --- | --- | --- |
| 相同 key + 相同 payload | 返回首次完成结果，`Idempotency-Replayed=true` | 接受重放结果，不重复创建逻辑 Decision |
| 相同 key + 不同 payload | `409 IDEMPOTENCY_CONFLICT` | fail closed，不换 key 规避冲突 |
| 请求仍在处理 | `409 IDEMPOTENCY_IN_PROGRESS`、retryable | 使用原 key/body 重试 |
| 网络超时/可重试错误 | 状态未知或返回 retryable ErrorEnvelope | 最多 3 次传输尝试；仅更新 timestamp/nonce/signature |
| 重试耗尽 | 不推断业务失败 | 标记 UNKNOWN，禁止据此重复真实执行 |

completed Decision 幂等记录至少保留 7 天。传输重试不等于执行重试。

## 7. Deferred Roadmap

Production V1 不包含：

1. Execution Receipt Server 接口；
2. Event 同步接口；
3. Agent 注册中心；
4. 多租户；
5. 多实例调度。

这些能力未来必须经过新 Contract Gate，不得静默添加到 V1。

## 8. 规范性资产与本次变更边界

### AI-CS Server

- `contracts/AI-CS-Production-Gateway-Contract-V1.md`
- `contracts/schemas/channel-engine-gateway-server.v1.schema.json`
- `contracts/compatibility/channel-engine-gateway-v1.md`
- `backend/app/gateway/contract.py`
- `backend/app/gateway/service.py`
- Gateway contract/server tests

### Channel Agent

- `docs/AI-CS-Production-Gateway-Contract-V1.md`
- `schemas/ai-cs-channel-engine-gateway-contract-v1.schema.json`
- `src/channel_engine/gateway/contract.py`
- `src/channel_engine/gateway/client.py`
- Gateway fake/mock 只做相同 wire projection
- Gateway contract/client/integration tests

未修改 AI answer 算法、RAG、Prompt、商品数据、数据库 schema、Browser/Session/Execution 状态机，也未连接真实 PDD。

## 9. Compatibility Validation

| Gate | 结果 | 证据 |
| --- | --- | --- |
| 双方 Schema 完全一致 | PASS | 解析后对象 equality=`true` |
| Schema hash 锁定 | PASS | 双方 contract tests 均断言 `e5ac64...f4b5` |
| 双方规范文档一致 | PASS | byte equality=`true`；文档 SHA-256=`a0eb76918b5be7c3f197bd82a96d7bd45fd9b4d61985b3866b156d9eab84a7d9` |
| HMAC 字节级兼容 | PASS | Server/Agent 已知向量测试输出相同 signature |
| AI-CS Gateway 定向测试 | PASS | 26 passed |
| Channel Agent Gateway 全受影响测试 | PASS | 85 passed，305 deselected |
| AI-CS Backend 全量回归 | PASS | 134 passed，3 skipped（隔离 real-runtime tests） |
| Channel Engine 全量回归 | PASS | 390 passed |
| Patch whitespace | PASS | 两仓库 `git diff --check` 均为 0 |

## 10. 风险与下一 Gate

1. 两仓库当前都有大量既有 dirty 候选资产。本次 Contract Freeze 没有替这些资产建立 Git Release；严禁使用 `git add .`。
2. 正式合并前必须按本报告“规范性资产”清单精确暂存，复核没有混入 PDD 实验、Sandbox、运行证据或业务代码。
3. HMAC secret 管理、TLS、证书、生产 Gateway 地址仍属于 Deployment Gate；当前没有配置或调用真实凭据。
4. Receipt/Event 的内部模型仍存在于 Channel Engine。后续开发必须遵守 Deferred 标记，不得误连为 V1 Server API。
5. Contract V1 任何 wire 字段变化必须重新计算 Schema hash、同步双方、通过双方 contract tests 并进入新版本评审。

## 11. 结论

Contract 版本唯一、双方字段一致、认证与幂等语义一致、测试通过，且没有跨越 Server/Agent Owner 边界。

**Final Status：`GATEWAY_CONTRACT_V1_PRODUCTION_FROZEN`**
