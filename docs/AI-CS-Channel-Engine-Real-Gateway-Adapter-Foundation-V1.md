# 《AI-CS Channel Engine Real Gateway Adapter Foundation V1》

| 项目 | 值 |
|---|---|
| Foundation 状态 | **READY** |
| Adapter | `ProductionGatewayClient` |
| Transport | `HttpGatewayTransport` / HTTPX 0.28.1 |
| Contract | AI-CS Gateway Contract V1 / `1.0` |
| 验证环境 | MockTransport + 进程内 Mock AI-CS |
| Production 默认 | **DISABLED** |
| 真实 AI-CS 请求 | `0` |
| 实现日期 | 2026-08-04 |
| 最终状态 | `CHANNEL_ENGINE_REAL_GATEWAY_READY` |

## 1. 范围与原则

本 Foundation 建立真实 AI-CS HTTP 接口的适配能力，但不建立生产连接。验证链路为：

```text
Channel Engine
      |
      v
ProductionGatewayClient
      |
      v
Gateway Contract V1 validation + HMAC authentication
      |
      v
HttpGatewayTransport
      |
      v
httpx.MockTransport
      |
      v
Local MockAICSServer
```

测试中的 staging/production 域名均使用保留的 `.invalid` 后缀，并由 `httpx.MockTransport` 在进程内截获，不执行 DNS、TCP、TLS 或外部 HTTP。Mock 环境只允许 loopback host。

当前应用默认仍构造 `AICSGatewayClient -> MockAICSTransport -> MockAICSServer`。本任务没有把 `ProductionGatewayClient` 自动接入应用启动流程，`Settings.real_gateway_enabled` 保持 `false`。

## 2. Adapter 设计

### 2.1 ProductionGatewayClient

`ProductionGatewayClient` 继承冻结契约客户端的行为并组合 HTTP transport：

```python
class ProductionGatewayClient(AICSGatewayClient):
    def request_decision(self, request: DecisionRequest) -> DecisionResponse: ...
    def health_check(self) -> GatewayHealth: ...
    def close(self) -> None: ...
```

构造参数：

| 参数 | 语义 |
|---|---|
| `GatewayAdapterConfig` | 环境、base URL、client/key ID、timeout、production 安全闸 |
| `secret: bytes` | 运行时注入的 HMAC secret，不进入 config/repr |
| `http_client` | 可注入 HTTPX client；测试使用 MockTransport |
| `GatewayRetryPolicy` | 1–3 次 Contract V1 传输尝试 |
| clock/nonce/sleeper | 可测试的认证与可靠性端口 |

Client 继续复用已验证能力：

- `DecisionRequest` 出站 schema validation；
- HMAC-SHA256 Authentication Metadata；
- request/correlation/idempotency identity；
- `DecisionResponse`、success header 与 identity 回显验证；
- 非 2xx `ErrorEnvelope` 和 HTTP/error-code 映射；
- timeout、retry、Retry-After 与幂等重放；
- `requires_approval=true` 安全闸；
- timeout outcome unknown 时禁止自动执行。

## 3. HTTP Transport

`HttpGatewayTransport` 实现现有 `GatewayTransport` Protocol：

```python
def request(
    *,
    method: str,
    path: str,
    body: bytes,
    headers: Mapping[str, str],
    timeout_seconds: float,
) -> GatewayTransportResponse: ...
```

### 3.1 传输规则

| 规则 | 实现 |
|---|---|
| HTTP client | HTTPX sync client |
| TLS | staging/production 强制 HTTPS；默认 `verify=True` |
| Proxy isolation | 自建 client 使用 `trust_env=False` |
| Redirect | `follow_redirects=False`；任何 3xx fail closed |
| Query/fragment | Gateway path 禁止 query 与 fragment |
| Decision deadline | 默认 15 秒，并传入 HTTPX timeout |
| Body | 使用已经 contract-validated 的固定 UTF-8 bytes |
| Headers | HMAC、body hash、contract/request/correlation/idempotency metadata |
| Response | status、原始 bytes、headers 映射回 transport response |

HTTP Transport 本身不解释业务 JSON；Contract Client 在 transport 边界之外执行严格 schema 和业务不变量校验。

### 3.2 错误映射

| HTTP/Transport 情况 | 映射 |
|---|---|
| HTTPX timeout | `GatewayTransportTimeout` |
| timeout 尝试耗尽 | `AICSGatewayTimeout(outcome_unknown=true)` |
| HTTPX connect/transport failure | `GatewayTransportError`，耗尽后 `GatewayUnavailable` |
| 有效非 2xx Error Envelope | `AICSGatewayRequestFailed` |
| 无效 response/error schema | `GatewayContractViolation` |
| status/error-code 不一致 | `GatewayContractViolation` |
| redirect | `GatewayContractViolation`，不跟随 Location |
| 不安全 path/timeout | 在 HTTP request 前 fail closed |

网络/timeout retry 始终复用同一业务 body、request ID、correlation ID 和 idempotency key；每个 attempt 只更新认证 timestamp、nonce 与 signature。

## 4. Environment Isolation

### 4.1 环境矩阵

| Environment | URL 规则 | 默认行为 |
|---|---|---|
| `mock` | 仅 `localhost`、`127.0.0.1`、`::1`；HTTP/HTTPS | 默认环境 |
| `staging` | 必须是 HTTPS；需要显式 base URL | 可显式构造 |
| `production` | 必须是 HTTPS；需要显式 base URL 和 enable flag | 默认拒绝 |

所有环境共同拒绝：

- URL 内嵌 username/password；
- query string 或 fragment；
- path prefix；
- 相对 URL；
- 不符合 Contract ID 格式的 client ID/key ID；
- 非正 timeout；
- 非布尔 production enable 值。

### 4.2 Production 安全闸

```text
environment == production
        |
        v
production_enabled == true ?
        | no
        v
ProductionGatewayDisabled
```

默认 `production_enabled=false`。专项测试验证：

1. 未 enable 的 production config 无法创建 transport；
2. 显式 enable 后只能使用 HTTPS；
3. 可在 MockTransport 下构造 production adapter；
4. 构造测试的 HTTP request count 为 `0`。

因此“支持 production”只表示代码具备受保护的适配结构，不表示本任务授权或执行生产连接。

### 4.3 环境变量

`GatewayAdapterConfig.from_env()` 支持：

| 环境变量 | 默认/约束 |
|---|---|
| `CHANNEL_ENGINE_GATEWAY_ENVIRONMENT` | `mock` |
| `CHANNEL_ENGINE_GATEWAY_BASE_URL` | mock 默认 `http://127.0.0.1:18021`；其他环境必须显式提供 |
| `CHANNEL_ENGINE_GATEWAY_CLIENT_ID` | `channel-engine` |
| `CHANNEL_ENGINE_GATEWAY_KEY_ID` | `foundation-http-key` |
| `CHANNEL_ENGINE_GATEWAY_TIMEOUT_SECONDS` | `15` |
| `CHANNEL_ENGINE_GATEWAY_PRODUCTION_ENABLED` | `false`，必须使用明确布尔值 |

HMAC secret 故意不属于 `GatewayAdapterConfig`，也没有在该 loader 中从环境读取。未来部署必须由 secret manager 在进程边界注入 bytes，并执行轮换与吊销策略。

## 5. Authentication 与 Contract Validation

HTTP Adapter 不修改 Gateway Contract V1。Decision request 使用冻结路径：

```text
POST /gateway/v1/decisions
```

每次 request 包含：

- `Authorization: HMAC-SHA256 Credential=<client_id>/<key_id>,Signature=<...>`；
- `X-AI-CS-Contract-Version: 1.0`；
- `X-AI-CS-Timestamp`、`X-AI-CS-Nonce`；
- `X-AI-CS-Content-SHA256`；
- `X-Request-ID`、`X-Correlation-ID`、`Idempotency-Key`；
- `Content-Type: application/json`。

本地 Mock AI-CS 验证 HMAC、body hash、clock window、nonce replay、header/body identity 与 strict `DecisionRequest`。Client 验证 strict `DecisionResponse` 或 `ErrorEnvelope`。

Contract 源文件和 checked-in schema 均未修改。

## 6. Health Integration

`ProductionGatewayClient.health_check()` 通过 HTTP Transport 请求 `/health`，严格验证：

| 字段 | 验证意义 |
|---|---|
| `status` | 服务 `HEALTHY` / `UNHEALTHY` |
| `service` | 服务身份 |
| `contract_version` | 必须等于 `1.0` |
| `gateway_version` | Gateway 实现版本；HEALTHY 时必填 |
| `capability_version` | Decision 能力版本；HEALTHY 时必填 |
| `reachable` | transport 可达性 |
| `real_ai_cs_connected` | 本地 Mock 明确为 `false` |
| `checked_at` | 带时区 timestamp |

错误 contract version、缺失 capability version、无效 schema、非 200 或 transport failure 均返回 fail-closed `UNHEALTHY`，不会抛出包含敏感正文的健康异常。

## 7. Mock/Local HTTP Integration

专项测试使用 `httpx.MockTransport` 将 HTTP request 交给 `MockAICSServer.handle_request()`：

```text
FakePDDAdapter
  -> ConversationService
  -> ProductionGatewayClient
  -> HttpGatewayTransport
  -> httpx.Request
  -> MockTransport
  -> MockAICSServer
  -> httpx.Response
  -> Contract DecisionResponse
  -> WAITING_APPROVAL
```

### 7.1 Decision / Response

验证：

- HTTP method/path/body；
- HMAC 和全部 Contract headers；
- Mock AI-CS request/compute count=`1`；
- Message=`COMPLETED`；
- Decision=`WAITING_APPROVAL`；
- `requires_approval=true`；
- Executor call=`0`；
- Channel send call=`0`。

### 7.2 Error

Mock AI-CS 返回 `403 AUTHORIZATION_DENIED` Error Envelope：

- 映射为 `AICSGatewayRequestFailed`；
- non-retryable，attempt=`1`；
- Conversation transaction 回滚；
- 不创建 Execution；
- Worker 无任务；
- Executor/Channel send 均为 `0`。

此外专项测试覆盖 ReadTimeout、ConnectError、无效 response schema、redirect 和 health version/capability mismatch。

## 8. 测试结果

验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_real_gateway_http_adapter.py tests\integration\test_real_gateway_adapter.py -q
.\.venv\Scripts\python.exe -m pytest --cov=channel_engine --cov-report=term-missing -q
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

当前结果：

- Real Gateway HTTP Adapter 专项：`24 passed`；
- 全量：`105 passed`，`0 failed`；
- 总覆盖率：`91%`；
- Mock/Local HTTP Decision/Response/Error：PASS；
- production HTTP requests：`0`；
- 真实 AI-CS/平台/AI/自动发送：`0`。

测试运行存在一条来自 FastAPI TestClient 依赖层的 `StarletteDeprecationWarning`，不影响 Adapter 或安全边界。

## 9. Contract 无漂移

| 冻结文件 | SHA-256 |
|---|---|
| `gateway/contract.py` | `6E08DE8085B1C217EC16C6BFE1AA03E2951BBD507A4EE0B2552F6FA1C18D0F06` |
| Gateway Contract V1 schema | `B2DC7467B14FAAB4D976BB655EF260FE352267E95DD4757BF10035C97CFC5D75` |

Canonical contract test 继续验证 checked-in schema 与代码生成结果完全相等。

## 10. Quality Gates

| Gate | 结果 | 证据 |
|---|---|---|
| Gate 1：Adapter 完成 | PASS | ProductionGatewayClient + HttpGatewayTransport |
| Gate 2：Contract 验证 | PASS | request/response/error/header/HMAC/schema |
| Gate 3：Mock/Local AI-CS 连接 | PASS | HTTPX MockTransport 完整 Decision 链路 |
| Gate 4：错误处理通过 | PASS | timeout/connect/error/schema/redirect/health |

最终状态：`CHANNEL_ENGINE_REAL_GATEWAY_READY`
