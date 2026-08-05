# AI-CS Production Server Runtime RC V1 Task Card

| 字段 | 内容 |
| --- | --- |
| 需求 ID | R013 |
| 日期 | 2026-08-05 |
| Owner | AI-CS Production Server Engineer；A/OPS 主责，C Console 与 Contracts 受影响复核 |
| 状态 | `DONE` |
| 目标 Gate | `AI_CS_SERVER_RC_READY` |

## 目标

在不改动 R006、R009、RAG、Prompt、B 客服语义、商品数据库且不连接真实 PDD/生产 Channel Engine 的前提下，将 AI-CS Core、Gateway Server 和 Operations Console 整理为可一键启动、可检查、可安全停止的 Production MVP Server Runtime Candidate。

## 完成标准

1. 保留既有 `start/status/stop_ai_customer_service.ps1`，新增 Production Server wrapper。
2. Gateway 启动检查提供签名 Health、实现版本和冻结 Contract `1.0`。
3. 统一配置覆盖 Gateway enable、Core/Gateway bind、secret reference 和 runtime mode；版本化配置不含明文 secret。
4. Operations Console 显示 Server/Gateway 状态、实现版本和 Contract 版本。
5. Gateway Health、Decision、Contract、start/status/stop、A 全量、C R006/R009 定向和 Admin 回归通过。

## 保护与边界

- 保护锚点仍为 `0b3367f85999f1dc840accf23742c290eb53746b`，当前 HEAD 与其一致。
- 本轮不 reset/rebase/commit/tag/push，不清理既有 R011/R012/T4 dirty Candidate。
- Production Gateway wire `1.0` 与 canonical SHA `e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5` 不变。
- 新增 `ai-cs.server-runtime-console.v1` 是本机 A-to-C 只读 additive contract，不是 Channel Engine production route。

## 验收证据

- Gateway/Runtime/Contracts 专项：`36 passed`。
- A 全量：`138 passed, 3 skipped`；跳过项均为显式 opt-in 真实模型/真实 C 服务 E2E。
- C R006/R009 定向：`25 passed`，使用测试临时数据库。
- Operations Console：`76 passed`，typecheck 与 production build 通过。
- Windows OPS：`11/11` suites 通过；新 wrapper 在隔离夹具完成 start/status/stop，PowerShell HMAC 与冻结测试向量一致。
- Shared contracts：`7 passed`；`17 schemas valid`。

## Gate

`PASS / AI_CS_SERVER_RC_READY`

该 Gate 表示源码与隔离生命周期验证达到 Server RC 条件；不表示已创建发布提交、已部署、TLS/外部访问控制/正式 secret manager 已验收，或已连接生产 Channel Engine/PDD。
