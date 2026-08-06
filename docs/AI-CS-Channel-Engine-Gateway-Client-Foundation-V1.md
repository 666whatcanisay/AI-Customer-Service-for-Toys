# 《AI-CS Channel Engine Gateway Client Foundation V1》

| 项目 | 值 |
|---|---|
| Foundation 状态 | **READY** |
| Client | `AICSGatewayClient` |
| Server | `MockAICSServer` |
| Transport | `MockAICSTransport`，仅进程内调用 |
| Gateway Contract | V1 / `1.0`，保持冻结 |
| 真实 AI-CS 连接 | **DISABLED** |
| 实现日期 | 2026-08-04 |
| 最终状态 | `CHANNEL_ENGINE_AI_GATEWAY_READY` |

## 1. 范围与完整链路

本 Foundation 建立如下本地闭环：

```text
FakePDDAdapter
      |
      v
NormalizedMessage
      |
      v
ConversationService
      |
      v
AICSGatewayClient
      |
      | Gateway Contract V1 bytes + HMAC metadata
      v
MockAICSTransport
      |
      v
MockAICSServer
      |
      v
DecisionResponse (requires_approval=true)
      |
      v
Human Approval -> Execution Worker -> Fake Executor -> Receipt
```

`MockAICSTransport` 直接调用进程内 Server dispatcher，不打开 socket、不解析主机、不调用 HTTP，也不包含真实 AI-CS base URL。应用默认启动该闭环，但 `Settings.real_gateway_enabled` 始终为 `false`。

Execution Worker 仍只绑定 `FakeExecutor`，未绑定真实渠道或 `FakePDDAdapter.send_message()`。因此 Decision、Approval 和 Receipt 的产生不会自动发送客户消息。

## 2. Client 设计

### 2.1 公共接口

```python
class AICSGatewayClient:
    def request_decision(self, request: DecisionRequest) -> DecisionResponse: ...
    def health_check(self) -> GatewayHealth: ...

    # 兼容现有 ConversationService 的 AICSGateway port
    def decide(self, request: DecisionRequest) -> DecisionResponse: ...
```

Client 依赖可注入的 `GatewayTransport` Protocol，而不是依赖某个网络库：

```python
class GatewayTransport(Protocol):
    def request(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> GatewayTransportResponse: ...
```

V1 只提供 `MockAICSTransport`。未来真实 transport 不属于本 Foundation，接入前必须单独安全评审、配置 TLS/HMAC secret manager 和 egress allowlist。

### 2.2 request_decision 流程

1. 将 `DecisionRequest` 序列化为稳定 UTF-8 JSON bytes；
2. 使用冻结模型 `DecisionRequest.model_validate_json()` 做出站 schema 校验；
3. 对业务 body 计算 SHA-256，并检查 Client 本地已完成响应缓存；
4. 每次传输 attempt 生成新的认证 timestamp、nonce 和 HMAC signature；
5. 始终复用相同 body、request ID、correlation ID 和 idempotency key；
6. 只接受 HTTP `200` 的 `DecisionResponse`；
7. 校验成功 header、response schema 和三个 identity 回显字段；
8. 将首次成功响应按 idempotency key/fingerprint 缓存；
9. 同 key、同请求返回同一响应；同 key、异请求 fail closed。

Client 不解释或执行 `proposed_content`。Gateway Contract V1 强制 `requires_approval=true`，Conversation Runtime 只创建 `WAITING_APPROVAL` Decision。

### 2.3 health_check

`health_check()` 调用本地 transport 的 `GET /health`，返回严格 `GatewayHealth`：

- `HEALTHY`：Mock Server 可达、版本为 `1.0`；
- `UNHEALTHY`：transport 异常、非 200、响应 schema 或版本错误；
- 失败结果只记录异常类型，不记录异常正文、客户内容或认证 header；
- Mock 健康响应始终声明 `real_ai_cs_connected=false`。

## 3. Gateway Contract V1 映射与验证

### 3.1 路径与基础参数

| 项目 | 值 |
|---|---|
| Method | `POST` |
| Path | `/gateway/v1/decisions` |
| Content-Type | `application/json` |
| Contract header | `X-AI-CS-Contract-Version: 1.0` |
| Deadline | 15 秒 |
| Body 上限 | 64 KiB |
| 成功 | `200 DecisionResponse` |
| 失败 | 非 2xx `ErrorEnvelope` |

### 3.2 认证元数据

`GatewayRequestSigner` 完整映射冻结的 `AuthenticationMetadata`：

- `Authorization: HMAC-SHA256 Credential=<client_id>/<key_id>,Signature=<signature>`；
- `X-AI-CS-Timestamp`、`X-AI-CS-Nonce`；
- `X-AI-CS-Content-SHA256`；
- `X-Request-ID`、`X-Correlation-ID`、`Idempotency-Key`；
- HMAC-SHA256 使用冻结 canonical signing text；
- secret 至少 32 bytes，并通过 dataclass `repr=False` 防止普通对象输出泄露。

Mock Server 验证：认证字段存在性、contract version、Authorization 格式、时间窗、body hash、credential、constant-time signature compare 和 10 分钟 nonce 防重放。应用使用 `secrets.token_bytes(32)` 在进程启动时生成仅供本地 Mock 的临时 secret；源码、配置和文档中没有可用凭据。

### 3.3 Request / Response / Error Envelope

| Artifact | 校验 |
|---|---|
| `DecisionRequest` | strict JSON schema、未知字段拒绝、header/body ID 一致、时区与字段约束 |
| `DecisionResponse` | strict JSON schema、action/content 不变量、`requires_approval=true` |
| Response identity | `request_id`、`correlation_id`、`idempotency_key` 必须逐字回显 |
| Success headers | contract version、request/correlation ID、`Idempotency-Replayed` |
| `ErrorEnvelope` | 所有非 2xx 必须可解析为冻结模型 |
| Error status | HTTP status 必须与 `GatewayErrorCode` 固定映射一致 |
| Rate limit | HTTP `Retry-After` 必须等于 envelope `retry_after_seconds` |

本任务没有修改：

- `src/channel_engine/gateway/contract.py`；
- `schemas/ai-cs-channel-engine-gateway-contract-v1.schema.json`；
- Gateway Contract V1 API、字段、状态码或错误码。

## 4. Mock AI-CS Server

`MockAICSServer` 只实现冻结的 Decision route 和本地 health route。其行为通过 `MockDecisionBehavior` 注入：

| Mode | 行为 |
|---|---|
| `SUCCESS` | 生成并原子缓存 Contract V1 `DecisionResponse` |
| `ERROR` | 返回配置的 Contract V1 `ErrorEnvelope` 与对应 HTTP status |
| `TIMEOUT` | 不返回 transport response，由 Mock transport 转换为 timeout |
| `TIMEOUT(commit_before_timeout=true)` | 先缓存成功结果再超时；同键重试获得 `Idempotency-Replayed: true` |

所有 Mock Decision 明确包含：

```json
{
  "mode": "MOCK",
  "real_ai_cs_called": false,
  "automatic_execution_authorized": false
}
```

Server 维护 request、compute、replay、error 和 timeout 计数，便于测试断言。它不导入 AI SDK、不调用模型、不访问网络，也不修改 AI-CS。

### 4.1 Mock 幂等

Decision route 固定为 `POST /gateway/v1/decisions`，因此其去重记录以 `(authenticated client_id, idempotency_key)` 保存，并对规范化业务 payload 做 SHA-256 fingerprint：

- 同 key、同 fingerprint：返回首次完成的同一 Decision，compute count 不增加；
- 同 key、异 fingerprint：`409 IDEMPOTENCY_CONFLICT`；
- ERROR 不进入成功缓存；
- timeout 前已提交的结果进入成功缓存，可由同键重放恢复；
- nonce 不参与业务 fingerprint，每个 retry attempt 必须使用新 nonce。

## 5. Timeout、Retry 与错误处理

### 5.1 Retry Policy

`GatewayRetryPolicy` 固定约束：

- `max_attempts` 为 1–3，不能突破 Gateway Contract V1 上限；
- 默认 Decision deadline 为 15 秒；
- 网络/transport failure 和 `ErrorEnvelope.retryable=true` 才允许重试；
- 指数退避加 jitter；
- `Retry-After` 是最小等待时间；
- 422、认证/授权、版本、幂等冲突等非重试错误立即终止；
- 每个 attempt 更新认证字段，但不得修改业务 body 或业务 identity。

### 5.2 Client 错误

| 错误 | 语义 |
|---|---|
| `GatewayContractViolation` | response/header/error envelope 不符合冻结契约；fail closed |
| `AICSGatewayRequestFailed` | 收到有效 Error Envelope；保留 status、code、attempts |
| `GatewayUnavailable` | 普通 transport failure 达到尝试上限 |
| `AICSGatewayTimeout` | 所有 attempt 均无响应；结果未知，`outcome_unknown=true` |
| `IdempotencyConflict` | Client 或 Server 发现同 key 异 payload |

### 5.3 UNKNOWN 安全规则

Gateway timeout 不能证明 AI-CS 未处理请求。Client 只使用原 idempotency key 重放，不生成新 key。

若尝试耗尽：

1. 抛出 `AICSGatewayTimeout`；
2. 当前 Conversation transaction 回滚；
3. 不创建 Decision、Approval 或 Execution；
4. Execution Worker 没有任务可领取；
5. Fake/真实 Channel send 均不会被调用。

这与 Execution Runtime 的 UNKNOWN 规则一致：传输重试不等于执行重试，任何 UNKNOWN 都禁止自动执行。

## 6. 应用集成

Foundation App 默认构造：

```text
runtime-generated mock secret
  -> GatewayRequestSigner
  -> AICSGatewayClient
  -> MockAICSTransport
  -> MockAICSServer
```

本地审计对象通过 application state 暴露：

- `application.state.ai_cs_gateway`；
- `application.state.gateway_client`；
- `application.state.mock_ai_cs_server`。

测试或现有调用仍可向 `create_app(gateway=...)` 注入符合 `AICSGateway` port 的实现。该扩展点不代表真实连接已获授权。

## 7. 测试结果

新增专项测试覆盖：

- Client SUCCESS、`request_decision()`、兼容 `decide()` 与 health；
- Request/Response/Error Envelope strict validation；
- HMAC、版本、body hash、credential、nonce replay；
- route、method、media type、64 KiB、无效 JSON 与 schema 拒绝；
- Client 本地幂等、跨 Client Server replay 与冲突；
- retryable ERROR 后成功；
- non-retryable ERROR 不重试；
- RATE_LIMITED 尊重 `Retry-After`；
- timeout 尝试耗尽与 unknown 标记；
- timeout-after-commit 的同键恢复；
- 普通 transport unavailable 重试耗尽；
- response identity、header、status/code、Retry-After 不匹配时 fail closed；
- Fake Channel -> Conversation -> Client -> Mock AI-CS -> Decision -> Approval -> Execution -> Receipt；
- Gateway TIMEOUT 不创建 Execution、不调用 Executor、不发送 Channel message；
- 原有 Contract、Adapter、Runtime、Lease、Receipt、Outbox 与 Recovery 回归。

验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_ai_cs_gateway_client.py tests\integration\test_ai_cs_gateway_flow.py -q
.\.venv\Scripts\python.exe -m pytest --cov=channel_engine --cov-report=term-missing -q
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

当前结果：

- Gateway Client/Mock 新增专项：`17 passed`；
- 全量：`76 passed`，`0 failed`；
- 总覆盖率：`90%`；
- 真实 AI-CS、真实平台、浏览器、自动发送和 AI 调用：`0`。

测试运行存在一条来自 FastAPI TestClient 依赖层的 `StarletteDeprecationWarning`，不影响功能或安全边界，无测试失败。

## 8. Quality Gates

| Gate | 结果 |
|---|---|
| AICSGatewayClient request/health | PASS |
| Gateway Contract V1 request/response/error validation | PASS |
| HMAC metadata and replay protection | PASS |
| Mock SUCCESS/ERROR/TIMEOUT | PASS |
| Timeout/retry/idempotency | PASS |
| UNKNOWN no-auto-execution | PASS |
| Full Decision-to-Receipt integration | PASS |
| Frozen contract unchanged | PASS |
| Forbidden boundary audit | PASS |

最终状态：`CHANNEL_ENGINE_AI_GATEWAY_READY`
