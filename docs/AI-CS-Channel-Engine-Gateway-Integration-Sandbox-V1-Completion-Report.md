# AI-CS Channel Engine Gateway Integration Sandbox V1 完成报告

## 技术结论

Channel Engine 已通过真实本机 TCP/HTTP 边界接入受控 AI-CS Gateway Sandbox，完成 `Gateway Edge → Decision → Human Approval → Execution Lease → Fake Adapter → Receipt → Event` 闭环。Gateway Contract V1 wire schema 未修改；新增的 Trace 字段只属于 Channel Engine 本地可观测模型。

新增专项测试 **9 passed**，Gateway/Contract 兼容回归 **130 passed**，全仓回归 **421 passed**。唯一 warning 是既有 Starlette TestClient 对 httpx 的第三方弃用提示，与本次协议集成结论无关。

## 1. 集成架构

```text
Synthetic ChannelMessageV1
        ↓
Conversation Runtime
        ↓
GatewayClient.from_http
        ↓  Contract V1 + HMAC-SHA256
127.0.0.1 Sandbox Gateway Edge
        ↓
Controlled Mock AI-CS Gateway
        ↓
DecisionResponse (WAITING_APPROVAL)
        ↓  explicit human approval
Execution PENDING → lease claim → RUNNING
        ↓
Fake Execution Adapter
        ↓
Receipt + Execution Event → Gateway Edge
```

`SandboxGatewayEdgeServer` 使用标准库 `ThreadingHTTPServer` 建立真实 socket，不再依赖进程内 `MockTransport`。服务强制绑定 `127.0.0.1` 和随机端口，不能暴露为真实生产 Gateway，也不包含 AI-CS 业务逻辑。

## 2. Gateway Client Integration

生产接口沿用 `GatewayClient.from_http()`：

- `GatewayAdapterConfig` 冻结环境和 endpoint；本次使用 `MOCK + loopback`。
- `GatewayServiceIdentity` 只保存 `client_id`、`key_id`、`credential_ref`。
- `GatewayTokenProvider` 按请求解析短期签名材料；对象日志始终脱敏。
- `ProviderBackedGatewayAuthenticator` 对每次请求生成独立 nonce 和 HMAC-SHA256 签名。
- `HttpGatewayTransport` 禁用环境代理、重定向和非精确路径。
- Decision 与 Receipt/Event 使用独立、有界重试策略和相同 Circuit Breaker。

本阶段没有连接生产 AI-CS，也没有修改 AI-CS Server 或 Gateway Contract V1。

## 3. Decision 与 Approval Flow

合成 `ChannelMessageV1` 进入 Conversation Runtime 后，经真实 HTTP POST `/gateway/v1/decisions` 获得冻结 `DecisionResponse`。Decision 固定进入 `WAITING_APPROVAL`；此时数据库中不存在 Execution，Fake Adapter 调用数为 0。

只有显式调用 `approve(decision_id, approved_by=...)` 后，系统才记录 `Approval(APPROVED)` 并创建 `Execution(PENDING)`。Worker 使用原子数据库领取将 Execution 切换为 RUNNING，并把 `approval_id`、`worker_id`、`lease_token`、`lease_expires_at` 组成的 `ClaimedExecutionContext` 交给受控适配器。测试确认 lease 有效且绑定同一 approval/execution；lease token 不进入 Trace、HTTP evidence 或报告。

## 4. Receipt 与完整 Trace

执行结束必须生成不可变 Receipt，并通过真实 HTTP PUT 发布：

- `/gateway/v1/execution-receipts/{receipt_id}`
- `/gateway/v1/events/{event_id}`

Trace 现在支持完整标识链：

```text
message_id
  → decision_id
  → approval_id
  → execution_id
  → receipt_id
```

`GatewaySandboxTraceStore` 新增 `for_message()` 与 `for_approval()` 索引；跨 Trace 重复绑定会 fail closed。Trace 不记录客户消息正文、Authorization、签名材料或 lease token。

## 5. Authentication、Timeout、Retry 与 Idempotency

| 控制项 | 规则 | 验证结果 |
|---|---|---|
| Authentication | Contract V1 HMAC-SHA256、timestamp、nonce、body digest | PASS |
| Timeout | 3 次有界重试后抛出 outcome unknown | PASS |
| 401 | 错误签名返回 `AUTHENTICATION_FAILED`，不重试 | PASS |
| 403 | 权限拒绝返回 `AUTHORIZATION_DENIED`，不重试 | PASS |
| Duplicate Decision | 相同 idempotency key + 相同 payload 返回原 Decision | PASS |
| Duplicate Artifact | 相同 Receipt/Event 返回原 acceptance | PASS |
| UNKNOWN | Receipt 标记 reconciliation required，禁止自动重执行 | PASS |

重复 Decision 测试使用两个独立 HTTP Client，避免命中客户端内存缓存；Gateway 只计算一次 Decision，第二次由服务端幂等记录返回。401/403 都通过冻结 Error Envelope 解析，attempts 保持 1。

## 6. Failure Handling

### Gateway timeout

Gateway Edge 连续三次延迟超过客户端 deadline。客户端产生 `AICSGatewayTimeout(outcome_unknown=true)`，Trace 进入 `GATEWAY_UNKNOWN`，Decision、Approval、Execution 与 Receipt 均未创建，适配器调用数为 0。重试次数由策略限定，不会无限重试。

### Invalid signature / 401

客户端使用错误签名材料时，Gateway 验证失败并返回 Contract V1 `AUTHENTICATION_FAILED`。请求不重试，AI Decision 计算数为 0。

### Authorization denied / 403

受控 Edge 策略拒绝返回 Contract V1 `AUTHORIZATION_DENIED`。请求不重试，AI Decision 计算数为 0。

### UNKNOWN execution

Fake Adapter 返回 UNKNOWN 后只调用一次。系统持久化 UNKNOWN Receipt，标记需要人工对账；再次触发同一 execution 只重放原 Receipt/Event，Fake Adapter 不再调用，`assert_not_automatic_retry()` 明确拒绝自动重试。

## 7. Security

- Edge 仅监听 `127.0.0.1`，随机端口，仅用于测试进程生命周期。
- Edge evidence 只保留 method、path、request/correlation/idempotency IDs、body SHA-256、状态码及是否存在认证头。
- Evidence 模型没有 request body、headers、Authorization value、payload 或 customer message 字段。
- Credential 只以 `vault://...` reference 保存；测试 provider 的 repr 始终输出 `<redacted>`。
- 真实 PDD、真实客户消息、发送、退款、订单修改均未进入本次执行路径。

## 8. 测试结果

| 测试层 | 结果 |
|---|---:|
| 新增 Integration / Contract / Security | 9 passed |
| Gateway 与 Contract 兼容回归 | 130 passed，1 warning |
| 全仓回归 | 421 passed，1 warning |

新增覆盖：

1. 真实 HTTP + HMAC + Health + Decision + Approval + Lease + Receipt/Event。
2. 两个独立客户端的服务端幂等重放。
3. 三次超时后的 UNKNOWN 安全停止。
4. 错误签名 401。
5. 权限拒绝 403。
6. UNKNOWN execution 不自动重试。
7. 403 Error Envelope Contract V1 校验。
8. credential 与 Edge evidence 敏感信息隔离。

## 9. Contract 无漂移证明

冻结 schema 文件 SHA-256：

`fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`

本任务没有修改 `gateway/contract.py` 或冻结 JSON Schema。原 Contract 测试与新增真实 HTTP Contract Test 共同通过。`message_id`、`approval_id` 是本地 Trace 扩展，不进入 DecisionRequest、DecisionResponse、ExecutionReceipt、Event 或 ErrorEnvelope wire 定义。

## 10. 已知限制与下一步

- 当前 Gateway Edge 是 loopback sandbox，不是 AI-CS staging 部署，也未验证 TLS 证书链、企业网络代理或 DNS 故障。
- 本次认证材料来自测试 provider；正式受控环境应接入批准的 Windows Credential/Secret Provider，并验证轮换和过期。
- HTTP 路径已覆盖 Decision、Health、Receipt 和 Event，但尚未做长时间 soak、进程重启期间的 artifact delivery 演练。
- 下一阶段应在明确授权的 AI-CS staging 环境运行同一测试矩阵，仍保持 Fake Channel、Fake Execution Adapter 和人工审批，不接入 PDD。

Final Status: `CHANNEL_ENGINE_GATEWAY_INTEGRATION_READY`
