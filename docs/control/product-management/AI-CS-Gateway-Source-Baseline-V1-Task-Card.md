# AI-CS Gateway Source Baseline V1 Task Card

| 字段 | 内容 |
| --- | --- |
| 需求 ID | R012 |
| 提出时间 | 2026-08-05 |
| 来源 | AI Mission Brief V2 — Source Baseline Preparation |
| 当前状态 | `DONE` |
| Owner | A / AI-CS Gateway Server Engineer；Control/QA/Contracts复核 |
| 目标 Gate | `AI_CS_GATEWAY_SOURCE_BASELINE_READY` |

## 目标

在不改写保护锚点、不触碰R006/R009、RAG、B/C业务逻辑和正式数据的前提下，将R011 Gateway Candidate整理为可维护的Production MVP源码候选，冻结职责、文件清单、Contract覆盖、延后项和T4输入。

## 本轮允许与实际修改

- 允许：Gateway、contracts、Gateway tests、shared contract tests与`docs/**`。
- 实际：仅新增/更新`docs/**`治理资产；Gateway实现、contracts 0.6和测试代码只读审计，未继续修改。
- 禁止路径`frontend/**`、`extension/**`、`platform_backend/**`、`admin_web/**`、RAG核心、商品数据库和R006/R009业务逻辑相对保护锚点零差异。

## 保护基线

- 保护锚点：`0b3367f85999f1dc840accf23742c290eb53746b`。
- 当前HEAD仍精确等于保护锚点，Git对象类型为`commit`。
- 当前dirty worktree是尚未提交的Gateway Candidate与治理文档；本任务未reset、checkout、rebase、commit、tag、push或清理任何既有修改。

## 完成标准

1. 输出Gateway Current Capability Matrix。
2. 将源码分为Production Candidate、Deferred、Experimental。
3. 冻结Server只负责Decision、Health、Authentication、Idempotency，不负责Browser/PDD/Execution/Chrome。
4. 确认contracts 0.6覆盖DecisionRequest、DecisionResponse、GatewayHealth、ErrorEnvelope并记录缺口。
5. Gateway专项、shared contracts、A全量和R006/R009定向回归通过。
6. 明确T4只能做非生产集成与部署准备，不得直接连接生产Channel Engine。

## 验收证据

- Gateway专项：`24 passed`。
- Shared contracts：`6 passed`。
- A全量：`133 passed, 3 skipped`；跳过项为显式opt-in真实模型/C服务E2E。
- R006/R009定向：`26 passed`，使用仓库既有`platform_backend/.venv`和测试临时数据库。
- JSON Schema：`16 valid`，Draft 2020-12 schema check通过。
- `git diff --check`、JSON一致性、敏感文件与禁止路径边界在最终Gate复核通过。

## Gate

`PASS / AI_CS_GATEWAY_SOURCE_BASELINE_READY`

该状态表示源码候选范围已冻结并具备进入受控提交评审的条件，不表示Candidate已形成新commit/tag、已部署、TLS/secret manager已就绪、生产Engine已接通或Receipt/Event已实现。
