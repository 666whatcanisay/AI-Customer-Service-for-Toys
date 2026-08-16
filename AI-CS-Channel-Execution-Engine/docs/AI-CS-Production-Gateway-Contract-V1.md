# AI-CS Production Gateway Contract V1

| 项目 | 冻结值 |
| --- | --- |
| 状态 | **PRODUCTION FROZEN** |
| Wire 版本 | `1.0` |
| HTTP Major | `/gateway/v1` |
| Schema ID | `urn:ai-cs:channel-engine:gateway-contract:v1` |
| Canonical Schema SHA-256 | `e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5` |
| 冻结日期 | 2026-08-05 |

本文是 AI-CS Server 与 Channel Agent 之间 Production MVP V1 的唯一规范性通信契约。“必须”“禁止”“应当”分别表示 MUST、MUST NOT、SHOULD。本文、签入的 JSON Schema 和双方 contract tests 共同构成冻结基线；wire payload 结构以 Schema 为准，安全约束发生歧义时采用更严格规则。

## 1. Owner 与边界

```text
Channel Agent                                  AI-CS Server
Browser / Session / Adapter                    Decision / RAG / Knowledge
Execution / Local Receipt          HMAC        Gateway Server
          |                                     |
          +---- POST /gateway/v1/decisions ---->+
          +<--------- DecisionResponse ----------+
          +------ GET /gateway/v1/health ------->+
          +<----------- GatewayHealth -----------+
```

- AI-CS Server 负责生成建议，不控制 Chrome、渠道 Session 或渠道执行。
- Channel Agent 负责浏览器、Session、Adapter、执行和本地 Receipt，不访问商品数据库、Chroma、Prompt 或模型。
- `DecisionResponse` 不是执行命令；`requires_approval` 在 V1 恒为 `true`。
- V1 不授权自动发送、自动退款、订单修改或资金操作。

## 2. Production V1 路由

| 方法与路径 | 请求 | 成功响应 | 语义 |
| --- | --- | --- | --- |
| `POST /gateway/v1/decisions` | `DecisionRequest` | `200 DecisionResponse` | 生成一项待人工确认的客服建议 |
| `GET /gateway/v1/health` | 无 body | `200 GatewayHealth` | 返回 Gateway 契约和能力健康状态 |

所有请求必须携带 HMAC 认证。Decision 的所有非 2xx 响应必须返回 `ErrorEnvelope`。响应媒体类型为 `application/vnd.ai-cs.channel-engine.gateway-v1+json`；Decision 请求接受该类型，兼容窗口内也接受 `application/json`。

## 3. DecisionRequest

除 `context` 外均为必填；对象禁止未知顶层字段。

| 字段 | 类型 | 冻结语义 |
| --- | --- | --- |
| `contract_version` | const `1.0` | Wire 版本 |
| `request_id` | string | 逻辑请求稳定 ID，重试不变 |
| `idempotency_key` | string | Decision 去重键，重试不变 |
| `correlation_id` | string | 贯穿 Message、Decision 和后续人工流程 |
| `conversation_id` | string | Agent 会话 ID，不应包含客户 PII |
| `message_id` | string | 触发 Decision 的消息 ID |
| `context` | object，默认 `{}` | 最小化辅助上下文；扩展只能放在此对象内 |
| `customer_message` | string，1–8000 | 当前客户消息 |
| `requested_at` | RFC 3339 date-time | 首次逻辑请求时间，重试不变 |

AI-CS 生产 profile 要求 `context.ai_cs_scope` 包含 `tenant_id`、`platform`、`store_code`、`product_id`，`sku_id` 可为 `null`。缺失或无效时 fail closed，不回退到无商品上下文的旧接口。

## 4. DecisionResponse

全部字段必填；对象禁止未知顶层字段。

| 字段 | 类型 | 冻结语义 |
| --- | --- | --- |
| `contract_version` | const `1.0` | 与请求一致 |
| `request_id` | string | 回显请求值 |
| `idempotency_key` | string | 回显请求值 |
| `correlation_id` | string | 回显请求值 |
| `decision_id` | string | 逻辑 Decision 稳定 ID |
| `action` | `SUGGEST_REPLY` / `NO_ACTION` | 建议类型 |
| `proposed_content` | string / `null` | 建议文本；`NO_ACTION` 时必须为 `null` |
| `requires_approval` | const `true` | 强制人工确认安全闸 |
| `risk_level` | `LOW` / `MEDIUM` / `HIGH` | Server 对本次建议的风险等级 |
| `gateway_version` | string | Server Gateway 实现版本，不是 wire 版本 |
| `metadata` | object | 非控制性诊断信息，不得承载密钥或执行指令 |
| `decided_at` | RFC 3339 date-time | 决策产生时间 |

Agent 必须把 `proposed_content` 当作不可信文本展示，不得作为脚本、工具调用或自动执行指令。

## 5. GatewayHealth

健康响应禁止未知字段并冻结以下必填字段：

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `status` | `HEALTHY` / `DEGRADED` / `UNHEALTHY` | Gateway 综合状态 |
| `service` | string | 服务身份 |
| `contract_version` | const `1.0` | Wire 版本 |
| `version` | string / `null` | Gateway 实现版本 |
| `capabilities` | string[] | 当前公开能力标识 |
| `reachable` | boolean | HTTP Gateway 是否可达 |
| `real_ai_cs_connected` | boolean | 是否连接真实 AI-CS 决策能力 |
| `timestamp` | RFC 3339 date-time | 检查时间 |
| `details` | object | 安全、非敏感诊断信息 |

`status=HEALTHY` 只证明 Gateway 可用，不授权任何渠道执行。

## 6. ErrorEnvelope

结构固定为 `{ "contract_version": "1.0", "error": { ... } }`。`error` 必须包含：

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `error_code` | `GatewayErrorCode` | 稳定、机器可判断的错误码 |
| `message` | string | 安全说明，不含堆栈、密钥或内部路径 |
| `request_id` | string / `null` | 可安全识别时回显 |
| `retryable` | boolean | 是否允许用原幂等键重试传输 |
| `details` | object | 安全的机器可读补充信息 |

同时保留规范字段 `error_id`、`correlation_id`、`retry_after_seconds` 和 `occurred_at`。可重试错误仅限 `IDEMPOTENCY_IN_PROGRESS`、`RATE_LIMITED`、`INTERNAL_ERROR`、`SERVICE_UNAVAILABLE`、`DEADLINE_EXCEEDED`；其余错误必须 `retryable=false`。

## 7. HMAC Authentication

### 7.1 Headers

- `Authorization: HMAC-SHA256 Credential=<client_id>/<key_id>,Signature=<base64url-signature>`
- `X-AI-CS-Contract-Version: 1.0`
- `X-AI-CS-Timestamp: <RFC3339 UTC>`
- `X-AI-CS-Nonce: <base64url nonce>`
- `X-AI-CS-Content-SHA256: <lowercase hex sha256 of raw body>`
- `X-Request-ID`
- `X-Correlation-ID`
- `Idempotency-Key`

### 7.2 Canonical signing string

使用 UTF-8，字段之间为单个 LF，末尾不得有 LF：

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

`signature = BASE64URL_NO_PADDING(HMAC_SHA256(secret, canonical_string))`。Secret 至少 256 bit；不得进入源码、日志、Schema、ErrorEnvelope 或业务 body。Server 必须校验 body hash、时间窗口、nonce 防重放并使用 constant-time signature comparison。默认允许时钟偏差为 ±300 秒，同一 client/key 的 nonce 10 分钟内不得复用。

双方 contract tests 使用同一已冻结测试向量：body `{"contract_version":"1.0"}`、secret `0123456789abcdef0123456789abcdef`、timestamp `2026-08-05T00:00:00Z`、nonce `bm9uY2UtZm9yLXRlc3QtMDAx`，期望 content hash 为 `84786626e94027a1c329b242d5c4c35eb285e80bd77cebb15c81fdb729c03227`，期望 signature 为 `FYWXv1salDMEWFLncJVmokCssvS0fdTEbhyxOAuC9uc`。

## 8. Idempotency 与 Retry

- 去重作用域：`(authenticated client_id, method, route family, idempotency_key)`。
- 同 key、同 canonical payload：返回首次完成的相同响应，不重新调用 AI；响应头 `Idempotency-Replayed: true`。
- 同 key、不同 payload：返回 `409 IDEMPOTENCY_CONFLICT`，禁止覆盖原结果。
- 同 key 尚在处理：返回 `409 IDEMPOTENCY_IN_PROGRESS`，客户端只可用原 key 重试。
- 网络超时或 `retryable=true` 时，Agent 最多进行 3 次传输尝试；body、request ID、correlation ID、idempotency key 和 `requested_at` 必须不变，每次尝试必须更新 timestamp、nonce 和 signature。
- 超时耗尽后的结果为 UNKNOWN，不得创建新 key 猜测重发，不得据此重复真实渠道执行。
- Server 的 completed Decision 幂等记录至少保留 7 天。

## 9. 版本策略

- URI、header 和 body 的 V1 版本必须一致，否则返回 `406 UNSUPPORTED_CONTRACT_VERSION`。
- V1 对未知字段 fail closed。
- 增删 wire 字段、修改类型/枚举/条件或改变安全语义，必须发布新的 contract 版本；不得静默修改 V1。
- Server 实现版本由 `gateway_version`/Health `version` 表达，不改变 wire `1.0`。
- 双方签入 Schema 必须完全相等，且 canonical SHA-256 必须匹配本文冻结值。

## 10. Deferred Roadmap（不属于 Production V1）

以下能力明确延后，不能通过扩展字段伪装成 V1 路由：

- Execution Receipt Server 接收接口；
- Event 同步接口；
- Agent 注册中心；
- 多租户 Gateway；
- 多 Agent 实例调度。

Channel Engine 内部可以保留 Receipt/Event domain model 和测试桩，但不得将其描述为 Production V1 对外协议。

## 11. 规范性资产

AI-CS Server：

- Schema：`contracts/schemas/channel-engine-gateway-server.v1.schema.json`
- Runtime contract：`backend/app/gateway/contract.py`
- Contract tests：`tests/contract/test_gateway_server_contract.py`、`backend/tests/test_gateway_contract.py`、`backend/tests/test_gateway_server.py`

Channel Agent：

- Schema：`schemas/ai-cs-channel-engine-gateway-contract-v1.schema.json`
- Runtime contract：`src/channel_engine/gateway/contract.py`
- Client：`src/channel_engine/gateway/client.py`
- Contract tests：`tests/contract/test_gateway_contract_v1.py`、`tests/unit/test_ai_cs_gateway_client.py`

最终状态：`GATEWAY_CONTRACT_V1_PRODUCTION_FROZEN`
