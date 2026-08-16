# 《AI-CS Channel Agent Source Baseline Report V1》

## 1. 技术结论

当前 dirty workspace 已完成资产分类和生产边界冻结，可以作为下一阶段 Channel Agent 组合工作的受控输入，但**当前仓库本身还不是可直接打包的 Production Candidate**。

审计快照包含 273 个 dirty 文件：24 个 tracked modifications、249 个 untracked files。逐文件分类结果为：

| 分类 | 文件数 | 对生产包的处理 |
|---|---:|---|
| Production Candidate | 85 | 58 个可直接作为组合输入，17 个必须拆分，10 个必须重建组合入口 |
| Deferred | 81 | 保留源码和文档，不进入本轮 Agent Package |
| Experimental | 26 | Fake、Mock、Sandbox、Discovery、脚本和 Evidence，强制隔离 |
| Test Only | 81 | 44 个进入 Required Test Baseline，37 个进入 Isolated Test Profile |
| **总计** | **273** | 所有文件均已分类 |

保护锚点 `b2c64d54987f1f066a02de8e9e667d5cc0f9857c` 可解析为 commit，审计时 `HEAD` 与该 SHA 完全一致。没有执行 reset、checkout、rebase、commit、删除或移动操作。

最重要的生产风险是当前 `channel_engine.app`、包级 `__init__.py` 和自动 package discovery 将 Production、Fake、PDD、Pilot、Sandbox 组合在同一导入图中。T4 不能复制整个 `src/channel_engine`，必须按本报告的 allowlist 重建 composition root 和 package manifest。

## 2. 审计范围、定义与证据

### 2.1 审计范围

审计对象是任务开始时 `git status --porcelain=v1 -uall` 返回的 273 个 dirty 文件，覆盖：

| 路径 | 文件数 |
|---|---:|
| `src/` | 130 |
| `tests/` | 81 |
| `docs/` | 41 |
| `scripts/` | 3 |
| `deploy/` | 6 |
| `evidence/` | 10 |
| `schemas/` | 1 |
| `pyproject.toml` | 1 |

逐文件机器可读清单：

`docs/baseline/AI-CS-Channel-Agent-Source-Baseline-V1-Asset-Inventory.csv`

- 行数：273（不含表头）。
- SHA-256：`6b6d2fdc8192ab6a61d70a82b43eb89ab8b3817cda5f9e298335fc812a40f589`。
- 字段：path、git_state、module、classification、package_disposition、test_baseline、rationale。

### 2.2 分类定义

- **Production Candidate**：能力属于 Channel Agent 冻结边界，可作为未来组合输入；不代表当前文件可原样进入 wheel。
- **Deferred**：有未来产品价值，但本轮因 PDD 专属、Pilot、未冻结外部接口、UI 鉴权或部署条件而延后。
- **Experimental**：Fake、Mock、Sandbox、Discovery、模拟脚本或 Evidence，只允许测试/研究使用。
- **Test Only**：只属于测试树；通过 Required 或 Isolated profile 控制运行，不进入 Runtime Package。

Production Candidate 进一步分为：

- **Direct Include（58）**：本轮文件级审计未发现直接的 Fake/PDD/Pilot 组合职责。
- **Split Required（17）**：同一文件同时包含生产抽象与 Fake、Mock、PDD 或 Pilot 符号，必须先拆分。
- **Recompose Required（10）**：当前入口、barrel export 或 package manifest 会主动加载被排除资产，必须重建。

### 2.3 方法

1. 验证保护 SHA 的 Git 对象类型及其与 HEAD 的关系。
2. 使用 `git status --porcelain=v1 -uall` 固定 273 文件审计总体。
3. 按目录、文件名和源码导入/符号扫描进行文件级分类。
4. 检查 Composition Root、package exports、Fake/Mock/PDD/Pilot 耦合。
5. 检查 Credential Reference 与敏感字段防护代码。
6. 检查 Channel Engine 是否包含 AI 模型、RAG、Prompt、Knowledge 或商品数据库实现。
7. 运行完整测试套件建立当前行为基线。

这是源码基线审计，不是生产安全认证、外部平台兼容认证或供应链审计。

## 3. 85 个 Production Candidate 的能力分布

### 3.1 Agent Runtime：6 个

候选能力：Agent node model、configuration domain、lifecycle、health/status API、server/browser/channel coordination。

当前限制：6 个文件全部需要 Split 或 Recompose。`agent/api.py` 同时加载 Dashboard UI 与 First Launch；config/models/runtime 仍含 PDD、Pilot 或 Fake 类型。T4 应提取纯 Agent lifecycle、config、health、store binding protocol，不复制 First Launch UI 和 Fake connector。

### 3.2 Session Runtime：9 个

候选能力：ChannelSession、state machine、heartbeat、credential reference、cursor/ACK、persistence、multi-instance manager、recovery。

文件处置：7 个 Direct Include、1 个 Split Required、1 个 Recompose Required。`credential.py` 中 Fake provider 必须移动到 test support；包级 export 不得再导出 FakeCredentialProvider。

### 3.3 Browser Runtime：8 个

候选能力：Chrome lifecycle、dedicated profile、page context、observation store、selector contract、session health 和 recovery。

文件处置：2 个 Direct Include、5 个 Split Required、1 个 Recompose Required。当前 observer/session/selectors/models/CDP 文件含 Fake 或 PDD-specific 符号；只保留通用 Browser contract、profile isolation、read-only observation 与 selector governance。

`browser/outbound.py` 已归 Deferred；`browser/adapter.py` 是 Mock PDD 实现，已归 Experimental。

### 3.4 Channel Adapter Framework：7 个

候选能力：adapter protocol、normalized message、lifecycle、registry、execution authorization boundary。

文件处置：5 个 Direct Include、1 个 Split Required、1 个 Recompose Required。`adapter_foundation.py` 同时包含 FakeChannelAdapter，T4 必须把 protocol/model 与 Fake implementation 分离。

### 3.5 Gateway Client 与 Contract：9 个

候选能力：Gateway Contract V1、request/response validation、auth/signature、HTTP transport、timeout、retry、circuit breaker、environment scope 和 trace identity。

文件处置：7 个 Direct Include（含 JSON Schema）、1 个 Split Required、1 个 Recompose Required。`gateway/integration.py` 中 Fake token provider 和 Mock gateway 必须拆到 test support；`gateway/__init__.py` 不得导出 FakeGateway、Mock server 或 Sandbox。

### 3.6 Execution 与 Durable Outbox：9 个

候选能力：approval boundary、queue、worker ownership、lease、recovery、receipt、ledger/outbox publisher。

文件处置：5 个 Execution Direct Include、1 个 Execution Split、1 个 Execution Recompose，以及 1 个 Outbox Split、1 个 Outbox Recompose。

`execution/fake_executor.py` 已归 Experimental。`worker.py` 目前从 fake executor 模块导入 claimed context，需要把生产 context 移到中立模块。`outbox/publisher.py` 中 FakeEventPublisher 必须拆出。

### 3.7 Observability Backend：7 个

候选能力：structured event、trace、repository、service、API、approval action boundary 和 runtime bridge。

全部 7 个为 Direct Include 候选。`observability/ui.py` 已归 Deferred：本轮 Production Candidate 只冻结 console backend，前端需等 Operator Authentication/RBAC 决策后再组合。

### 3.8 支撑平台能力：30 个

包括：Control Plane 6、Runtime Reliability 8、Persistence 5、Environment/Safety 4、Domain Model 2、Conversation Runtime 1、Health Monitor 1、Runtime Configuration 1、Composition Root 1、Package Metadata 1。

其中 `storage/orm.py` 混入 PDD WebSocket、PDD Safety、PDD Pilot 表，必须拆分核心 runtime schema 与 deferred schema；当前 `app.py` 和 `pyproject.toml` 必须重建，不能直接进入 Agent Package。

## 4. 81 个 Deferred 资产

| 模块 | 数量 | 延后原因 |
|---|---:|---|
| Documentation | 41 | 历史设计、完成报告和 Runbook；保留为参考但不属于 Runtime Package |
| PDD Prototype | 12 | 平台消息、selector、session、mapper 尚未经过真实平台契约验证 |
| PDD Pilot | 10 | 单店 Pilot 和 Live activation 依赖真实环境验证与单独授权 |
| Channel Adapter Framework（PDD） | 7 | Controlled send、observation、production safety、WebSocket 等仍是 PDD 专属实现 |
| Deployment Profiles | 6 | 当前仅 Mock/Staging/PDD 示例，不是冻结的 Production manifest |
| Agent Runtime | 3 | First Launch 和 UI 不属于最小生产 runtime，且缺少 Operator Auth/RBAC |
| Browser Runtime | 1 | Browser outbound action 本轮明确不进入生产组合 |
| Observability UI | 1 | Console frontend 延后到本地认证和权限模型冻结后 |

Deferred 不代表删除。所有资产原位保留，T4 不得通过 glob 或 package auto-discovery 将其带入 Agent wheel。

## 5. 26 个 Experimental 资产

| 模块 | 数量 | 隔离规则 |
|---|---:|---|
| Evidence | 10 | 仅审计留证，绝不打包 |
| Channel Fake/Sandbox/Discovery | 5 | 仅供测试与发现流程 |
| Gateway Fake/Mock/Sandbox | 3 | 仅供 contract/integration tests |
| PDD Prototype Fake/Observe/Discovery | 3 | 仅在 isolated profile 运行 |
| Discovery/Pilot scripts | 3 | 手工工具，不进入安装包或启动项 |
| Fake Executor | 1 | 仅测试使用 |
| Mock PDD Browser Adapter | 1 | 仅测试使用 |

Experimental 资产不得被 Production Composition Root import，不得作为 console script，不得作为 runtime fallback，也不得出现在 wheel 内容清单中。

## 6. 生产组合的 27 个拆分/重建阻断

### 6.1 Recompose Required：10 个

- `pyproject.toml`
- `src/channel_engine/app.py`
- `src/channel_engine/agent/__init__.py`
- `src/channel_engine/browser/__init__.py`
- `src/channel_engine/channel/__init__.py`
- `src/channel_engine/execution/__init__.py`
- `src/channel_engine/gateway/__init__.py`
- `src/channel_engine/outbox/__init__.py`
- `src/channel_engine/reliability/__init__.py`
- `src/channel_engine/session/__init__.py`

当前 `pyproject.toml` 使用 `setuptools.packages.find` 收集整个 `src`，且 `channel-engine`/`channel-agent` 都指向混合的 `channel_engine.app`。`app.py` 默认实例化 Fake Gateway、Fake Channel、Fake Executor、PDD Safety 和 Pilot Runtime。任何“直接 build wheel”都会违反生产边界。

### 6.2 Split Required：17 个

- Agent：`api.py`、`config.py`、`dashboard.py`、`models.py`、`runtime.py`
- Browser：`cdp_readonly.py`、`models.py`、`observer.py`、`selectors.py`、`session.py`
- Adapter：`adapter_foundation.py`
- Execution：`worker.py`
- Gateway：`integration.py`
- Outbox：`publisher.py`
- Reliability：`browser.py`
- Session：`credential.py`
- Persistence：`orm.py`

这些文件中的生产抽象可继续使用，但 Fake、Mock、PDD、Pilot 或实验 schema 必须移至 `tests/support`、`experimental/` 或 deferred adapter package。

## 7. Channel Agent 边界冻结

### 7.1 Channel Agent 负责

- Agent lifecycle、local runtime、configuration、health。
- Chrome process、dedicated profile、Browser session、read-only page observation。
- Channel Instance、Session、heartbeat、credential reference、cursor/ACK、recovery。
- Channel Adapter protocol、message normalization、lifecycle 和 registry。
- AI-CS Gateway Client、authentication、contract validation、timeout/retry/circuit breaker。
- Human Approval、Execution、lease/ownership、Receipt、Ledger、Durable Outbox。
- Local persistence、structured event、trace、observability backend。

### 7.2 Channel Agent 明确禁止

- AI 模型调用策略、模型选择或推理实现。
- RAG、Knowledge、Embedding、Vector Store。
- Prompt 模板或 Prompt 编排。
- 商品数据库、商品知识生成或业务知识管理。
- 绕过 AI-CS Gateway 自行生成客服回复。
- 真实 PDD 登录、真实渠道连接或真实发送作为默认能力。
- 保存明文 Cookie、Token、Password 或 Secret。

源码扫描未发现 OpenAI/模型/RAG/Prompt/Knowledge 实现进入 Channel Engine；Decision 仍通过 Gateway Contract 交互。Credential 模型保存 opaque reference，敏感字符串验证和日志/事件脱敏逻辑已存在。该结论不等同于独立 secret scanner 或供应链安全认证。

## 8. AI-CS-Agent 未来目录组合方案

本阶段不复制代码。T4 建议在独立 clean worktree 中建立显式 allowlist 组合：

```text
AI-CS-Agent/
├── pyproject.toml                  # 显式 package include；禁止全量 find
├── src/ai_cs_agent/
│   ├── composition/               # production-only composition root
│   ├── agent/
│   │   ├── runtime/
│   │   ├── config/
│   │   └── health/
│   ├── browser/
│   │   ├── lifecycle/
│   │   ├── profile/
│   │   ├── observation/
│   │   └── selector/
│   ├── session/
│   ├── adapter/
│   ├── gateway/
│   ├── execution/
│   ├── observability/
│   ├── persistence/
│   └── control/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   └── support/                    # Fake/Mock only
└── experimental/
    └── pdd/                        # 不进入 wheel
```

组合规则：

1. 生产代码只能依赖 protocol/port，不依赖 Fake implementation。
2. Production Composition Root 必须显式注入 Gateway、Credential Provider、Browser Driver、Adapter 和 Event Publisher。
3. 未提供生产实现时启动失败；禁止自动回退到 Fake。
4. PDD、Pilot、Discovery、Sandbox 必须使用独立 extras/profile，默认不可导入。
5. SQLite schema 只包含 core runtime 表；PDD/Pilot schema 使用独立 migration/package。
6. wheel 内容通过 allowlist 和 import scan 双重校验。

## 9. Test Baseline

### 9.1 Required：44 个

必须随 Production Candidate 进入 T4 验证：

- Unit：14
- Contract：5
- API：10
- Integration：15

覆盖 Agent lifecycle、Runtime、Session/Cursor/ACK、Credential boundary、Adapter protocol、Gateway contract/auth/retry、Execution/Lease/Receipt/Outbox、Observability/Event/Trace、Control Plane 与 persistence recovery。

Required 测试可以注入 Fake port 实现，但 Fake 源码只能位于 test support 或 test extra，不能因此进入 production wheel。

### 9.2 Isolated：37 个

- PDD contract/integration/prototype tests。
- Sandbox/Fake/Mock E2E。
- Discovery/Observe/Pilot tests。
- AI-CS local gateway test harness。

这些测试保留用于回归，但必须通过 marker、独立 test path 或 optional test dependency 隔离，不作为 production runtime dependency closure 的组成部分。

### 9.3 当前行为基线

2026-08-05 在保护锚点对应 workspace 上执行完整测试：

- `388 passed`
- 1 个 Starlette TestClient/httpx 弃用警告
- 无测试失败

## 10. 限制与稳健性检查

- 分类粒度是文件；17 个混合文件已经标记 Split Required，但没有在本阶段进行 symbol-level 拆分。
- 58 个 Direct Include 表示“未发现文件级实验耦合”，不是生产安全认证；T4 仍需 import closure、license、dependency 和 secret scan。
- 273 是任务开始时 dirty delta，不是整个 Git repository 的所有 tracked files。
- 文档、Evidence 和历史报告保留原位；本阶段没有验证其中所有历史声明。
- 没有连接真实 PDD、真实 AI-CS production、真实浏览器会话或真实客户数据。
- 未生成 wheel、EXE、installer 或 deployment artifact。

稳健性检查结果：

- Git anchor object 存在，HEAD 未变化。
- CSV 行数与 dirty snapshot 273 精确一致。
- 分类总和 `85 + 81 + 26 + 81 = 273`。
- package disposition 总和 `58 + 17 + 10 + 188 = 273`。
- test baseline 总和 `44 + 37 = 81`。
- 全量测试通过。

## 11. 下一步 T4 输入

T4 建议任务名：`Channel Agent Production Composition Extraction V1`。

输入：

- 保护 SHA：`b2c64d54987f1f066a02de8e9e667d5cc0f9857c`
- 本报告。
- 273 行资产清单及其 SHA-256。
- 58 个 Direct Include allowlist。
- 17 个 Split Required 清单。
- 10 个 Recompose Required 清单。
- 44 个 Required Test Baseline。

T4 必须完成：

1. 在独立 clean worktree/branch 中创建 production-only package composition。
2. 拆分 17 个混合文件的生产接口与 Fake/PDD/Pilot 实现。
3. 重建 10 个 composition/barrel/package files。
4. 使用显式 package allowlist，禁止 `find` 自动收集整个源树。
5. 建立 `tests/support` 与 `experimental/pdd` 隔离边界。
6. 验证 production import graph 不含 `.fake`、`.sandbox`、`.pilot`、`.pdd_*`、`.mock_server`。
7. 验证 wheel 内容不含 docs、scripts、deploy samples、evidence、tests 或 experimental assets。
8. 运行 44 个 Required tests、credential leakage scan、UNKNOWN/no-auto-retry 和 approval boundary tests。
9. 输出 composition manifest、wheel file list 和 dependency closure evidence。

T4 不得：连接真实 PDD、启用真实发送、修改 AI-CS、引入模型/RAG/Prompt/Knowledge、生成 EXE 或破坏保护锚点。

## 12. Quality Gate

- 代码未重构：通过。
- 现有资产未移动、未删除：通过。
- 未连接真实 PDD：通过。
- 未修改 AI-CS：通过。
- 未生成 EXE/wheel：通过。
- 保护锚点未改变：通过。
- 273 文件完成逐项分类：通过。
- Production/Deferred/Experimental/Test Only 边界完成：通过。

---

Final Status: `CHANNEL_AGENT_SOURCE_BASELINE_READY`
