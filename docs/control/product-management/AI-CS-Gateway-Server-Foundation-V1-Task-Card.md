# AI-CS Gateway Server Foundation V1 Task Card

| 字段 | 内容 |
| --- | --- |
| 需求 ID | R011 |
| 提出时间 | 2026-08-04 |
| 来源 | AI Mission Brief V2 — AI-CS Gateway Server Implementation |
| 当前状态 | `DONE` |
| Owner | A / AI-CS Gateway Server Implementation Owner |
| 目标 Gate | `AI_CS_GATEWAY_SERVER_READY` |

## 目标

在不改变 B 客服链路、`POST /api/chat`、RAG 核心、商品知识逻辑和模型的前提下，为 AI-CS 建立独立的 Channel Engine Gateway Contract V1 Server Foundation。

## 允许范围

- 新增 `POST /gateway/v1/decisions` 与 `GET /gateway/v1/health`。
- 新增严格 Request/Response schema、HMAC-SHA256 认证、nonce 防重放、持久化幂等、Decision Mapping 与统一 ErrorEnvelope。
- 新增 Gateway 专项、共享 Contract 与 `/api/chat` 回归测试。
- 增量更新共享 contracts 的 schema、version、changelog、兼容说明和受影响线复核。

## 禁止范围

- 不修改 B 前端或 B 调用路径。
- 不修改 `/api/chat` 语义、RAG/Prompt/模型、商品知识与数据库业务结构。
- 不实现自动发送、退款、订单修改或绕过人工审批。
- 不配置、调用或模拟已连接生产 Channel Engine。
- Phase 1 不实现 Execution Receipt 或 Event ingestion。

## 冻结 Contract 判定

Mission Brief 中的 `schema_version`、`request_key`、`message` 是概念名称；Gateway Contract V1 冻结 wire 字段分别为 `contract_version`、`idempotency_key`、`customer_message`。服务端严格实现冻结字段并拒绝旧名/别名，避免形成第二套 Contract。

AI-CS 在 Contract 允许的 `context` 扩展中要求 `context.ai_cs_scope`，复用既有 `FrozenChatContext` 的 tenant/platform/store/product/SKU 范围校验，禁止走无范围 legacy message 回退。

## 完成标准

1. 两个 Phase 1 路由存在且默认关闭；未配置时不影响 A/B 既有能力。
2. DecisionRequest 严格校验，header/body identity 一致，未知字段和旧别名被拒绝。
3. 所有有效路由要求 HMAC，校验 timestamp、nonce、raw-body SHA-256 和 constant-time signature；nonce 跨进程持久化防重放。
4. 六种现有 A action 映射到 Contract V1，所有 Decision 固定 `requires_approval=true`。
5. 非成功结果使用非 2xx 与统一 ErrorEnvelope。
6. 同 client/同 idempotency key/同 canonical payload 返回同一 Decision；不同 payload 返回 409；租约旧 owner 不能覆盖新 owner。
7. Gateway Contract/Auth/Idempotency/Error/Chat Regression 及 A/B 全量回归通过。
8. 共享 contracts 完成 0.6.0 additive 治理；明确 B/C 无代码变更及生产连接仍被禁止。

## 验收证据

- Gateway 专项：`24 passed`。
- A 全量候选：`133 passed, 3 skipped`；跳过项是既有显式真实模型 E2E，不属于本任务自动测试。
- Shared contracts：`6 passed`；16 个 JSON Schema 可解析。
- B 回归：`127 passed`，typecheck 与 production build 通过。
- 详细报告：[AI-CS Gateway Server Foundation V1](../../rag/AI-CS-Gateway-Server-Foundation-V1.md)。

## Gate 结论

`PASS / AI_CS_GATEWAY_SERVER_READY`

该 Gate 只表示源码 Foundation 与离线/合成契约测试就绪，不表示已部署、已完成 TLS/密钥托管、已接通生产 Channel Engine，也不替代 R003/R005/R007。
