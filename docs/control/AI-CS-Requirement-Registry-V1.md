# AI-CS Requirement Registry V1

> 文档类型：长期需求台账
>
> 版本：V1
>
> 台账所有者：Control / AI-CS System Architect
>
> 首次登记：2026-07-29
>
> 当前 Gate：`SHADOW_RUNTIME_PASS / PHASE_E2_ENTRY_READY / STANDARD_PORT_CUTOVER_NOT_AUTHORIZED / RECOVERY_RUNTIME_UNCHANGED`

## 1. 台账目标

本文件是 AI-CS 项目的需求级事实来源，用于回答四个问题：需求是否已经提出、是否已经实现、由谁负责、当前真正被什么阻塞。

所有未来需求必须遵循：

```text
提出
  ↓
登记
  ↓
分配
  ↓
开发
  ↓
验收
  ↓
关闭
```

任何 Agent 或窗口在设计、开发或修复前，必须先检索本台账。没有需求 ID、当前状态、负责模块、完成标准和前置 Gate 的工作，不得进入开发。

台账只管理需求事实，不替代 Git、运行基线、接口冻结、测试报告或 Pilot 运行记录。`DONE` 表示功能完成标准已有证据，不等于该功能已经进入统一、可复现的运行基线；统一基线问题由 R004 单独治理。

## 2. 状态定义

| 状态 | 定义 | 使用规则 |
| --- | --- | --- |
| `TODO` | 已登记、待处理 | 已有明确目标和完成标准，但尚未分配进入实现。 |
| `IN_PROGRESS` | 开发中或受控处理进行中 | 已明确负责人和当前工作入口；不能仅因讨论过或创建了窗口就进入此状态。 |
| `DONE` | 已完成 | 完成标准全部满足，并记录可复核的验收证据。 |
| `BLOCKED` | 被阻塞 | 目标仍有效，但存在已明确且当前无法绕过的前置条件。必须记录阻塞点和解除条件。 |
| `DEPRECATED` | 废弃 | 目标已取消、被替代或不再符合项目方向。必须记录替代需求或废弃原因。 |

“关闭”不是新的状态值：已验收需求以 `DONE` 关闭；取消或被替代的需求以 `DEPRECATED` 关闭。

允许的主要状态流转：

```text
TODO → IN_PROGRESS → DONE
  │          │
  └────┬─────┘
       ↓
    BLOCKED → IN_PROGRESS

TODO / IN_PROGRESS / BLOCKED → DEPRECATED
```

`DONE` 需求不得因为新窗口或相似描述被直接重新设计。若发生回归，优先登记关联缺陷；若目标实质变化，登记新需求并引用原需求 ID。

## 3. 每个需求的强制字段

| 字段 | 登记要求 |
| --- | --- |
| 需求 ID | 全局唯一，格式为 `R` 加三位数字；废弃后不得复用。 |
| 提出时间 | 使用首次提出日期；历史补录需标明补录日期。 |
| 需求名称 | 使用稳定的业务名称，不使用临时窗口名代替。 |
| 用户原始目标 | 保留用户希望解决的业务结果，不改写成技术方案。 |
| 业务背景 | 说明为什么需要该需求，以及它与现有能力的关系。 |
| 当前状态 | 只能使用本文件定义的五种状态。 |
| 负责模块 | 明确 Control、A、B、C、OPS、QA 或共享 contracts 的所有权。 |
| 影响范围 | 明确代码、接口、数据、运行环境和 Pilot 中哪些范围受影响。 |
| 完成标准 | 必须是可验收结果，不能只写“代码完成”或“页面完成”。 |
| 验收证据 | 记录测试、运行、文档、commit/PR 或人工验收；未完成时明确写“尚无”。 |
| 关联代码/文档 | 指向当前真实来源；未进入统一基线的来源必须显式标注。 |
| 防止重复错误规则 | 说明后续不能把什么重新当成新需求或采用什么错误解法。 |

## 4. 登记、分配与关闭规则

1. 新需求提出后，先按名称、业务问题、影响实体和目标结果检索本台账。
2. 与现有需求目标相同的，更新原需求，不创建重复 ID。
3. 已完成能力出现回归时，登记关联缺陷或恢复任务，不重新设计已完成结构。
4. 同一问题与其解决方案可以分开登记，但必须明确关系。例如 R003 是业务问题记录，R006 是解决该问题的交付任务。
5. 跨 B/C/A 的需求在进入 `IN_PROGRESS` 前，必须完成运行基线确认和 Interface Freeze；需要修改共享 contracts 时，还必须包含 schema、版本、changelog、兼容说明和受影响线复核。
6. 需求只有在验收证据可复核后才能进入 `DONE`。仅有设计稿、单线测试、Mock 成功或本地临时字段，不构成关闭证据。
7. 状态、完成标准、阻塞点或负责人变化时，同步更新本台账、当前状态摘要、控制面状态看板、变更记录、交接说明和 `machine-context.json`。

## 5. 当前需求总览

| ID | 需求名称 | 状态 | 负责模块 | 当前判断 |
| --- | --- | --- | --- | --- |
| R001 | C商品知识运营中心V2 | `DONE` | C | 已由 R004 收敛进入正式 Pilot 基线；不得重做结构。 |
| R002 | AI客服反馈沉淀闭环 | `DONE` | B、C、contracts | 已由 R004 按所有权收敛；真实 Pilot 效果由 R005 单独验证。 |
| R003 | C新增店铺/商品无法进入B客服 | `IN_PROGRESS` | Control、C、B，A 下游验证 | R006 V1.1验证已完成但仍有两个P0接口空白；Implementation和业务验收尚未开始。 |
| R004 | AI-CS运行版本统一 | `DONE` | Control、OPS、A/B/C、contracts | Recovery 分支、独立提交、contracts 0.2.0、全量测试和四服务同 SHA 运行均已建立。 |
| R005 | Customer Feedback Loop真实运行验证 | `TODO` | Control、OPS、QA、B/C/A | 等待统一基线与真实客服运行样本。 |
| R006 | Pilot Business Data Activation V1 | `TODO` | Control / Interface Owner、C、B，A 无变更 | V1.1验证为`CONDITIONAL PASS`；混合来源迁移映射与receipt响应/复核契约关闭前禁止Implementation。 |
| R007 | 网络环境导致客服无法访问5173 | `BLOCKED` | OPS、公司网络管理 | 当前判断是 VLAN / 端口 / 网络隔离，不是 AI-CS 代码问题。 |
| R008 | AI-CS Project Structure Simplification V1 | `IN_PROGRESS` | Control、OPS、A/B/C、QA | Phase E1影子运行PASS：Target四服务在15173/15174/18000/18011从同一SHA运行，独立数据路径、Admin实际路由、页面/API/模型均通过；Recovery标准端口与数据锚点未变化。E2标准端口切换尚未授权。 |

状态数量：`DONE=3`、`IN_PROGRESS=2`、`TODO=2`、`BLOCKED=1`、`DEPRECATED=0`。

## 6. 需求明细

### R001 — C商品知识运营中心V2

| 字段 | 内容 |
| --- | --- |
| 需求 ID | R001 |
| 提出时间 | 2026-07-29（历史能力补录） |
| 需求名称 | C商品知识运营中心V2 |
| 用户原始目标 | 让运营以“店铺 → 商品 → SKU”的业务方式管理 AI 知识。 |
| 业务背景 | C 原有能力包含目录、资料和审核，但运营需要中文业务展示、结构化知识维护、知识状态和缺口视角；内部 ID、技术字段和发布状态不能替代运营语义。 |
| 当前状态 | `DONE` |
| 负责模块 | C：`platform_backend/**`、`admin_web/**`、`docs/platform/**`。 |
| 影响范围 | C 商品知识中心、知识维护、知识资料、知识缺口和中文模板；不修改 B、A、Store/Product/SKU 底层模型或共享 contracts。 |
| 完成标准 | 运营可以按店铺、商品、SKU查看和维护知识；页面使用中文业务展示；六类知识模板可识别；资料状态与 AI 状态分离；知识缺口可按业务维度处理。 |
| 验收证据 | Recovery Commit `2cf1c3748285e0537667680833aab82dfc6f1596` 独立归档本能力；最终全量 C Backend `95 passed`，Admin `25 files / 54 tests passed`，typecheck 与 production build 通过。 |
| 关联代码/文档 | 正式来源为 Recovery 基线中的 `docs/platform/21_C商品知识运营中心V2.md`、`platform_backend/app/product_knowledge/`、`platform_backend/app/knowledge_materials/`、`admin_web/src/views/KnowledgeCenterView.vue`、`KnowledgeEditorView.vue`、`KnowledgeGapCenterView.vue`。 |
| 防止重复错误规则 | 后续不得重新设计商品知识结构，不得重建 Store/Product/SKU Master Data，不得把“未进入统一基线”误判为“功能未完成”。新增能力必须在现有店铺 → 商品 → SKU结构上增量提出。 |

### R002 — AI客服反馈沉淀闭环

| 字段 | 内容 |
| --- | --- |
| 需求 ID | R002 |
| 提出时间 | 2026-07-29（历史能力补录） |
| 需求名称 | AI客服反馈沉淀闭环 |
| 用户原始目标 | 客服使用 AI 产生的数据可以沉淀，并进入运营可处理的知识优化链路。 |
| 业务背景 | 客服的直接采用、修改后采用和未采用行为不能只停留在 B 页面；未采用问题需要进入 C 问题中心，经人工确认、知识补充和复验形成闭环。 |
| 当前状态 | `DONE` |
| 负责模块 | B：事件生产与严格回执；C：权威保存、AI问题中心、知识优化任务与复验；共享 `contracts/**`：事件 schema 和兼容说明；A 无本需求代码变更。 |
| 影响范围 | 客服采用状态、问题反馈、C AI问题中心、知识优化任务、人工复验、共享契约版本；不进入自动知识发布、自动 Prompt 修改或训练。 |
| 完成标准 | 采用/修改后采用/未采用均由 C 返回真实保存回执；未采用即时形成 AI 问题；运营可确认、处理、建立知识任务并记录改善或未改善；失败不得由 B 本地伪装成功。 |
| 验收证据 | Contracts `bd837b0b6af03c6b1e29a456c8aca047e98e971c`、C Provider `14ecf39dd726efe18be7218ebad6bf2a4f22a52b`、B Consumer `acfaa8b574d445cea6039ffa388d54661775b31f` 已独立归档；最终 C Backend `95 passed`、Admin `54 passed`、B `115 passed`，两端 typecheck/build 与 7 个 JSON Schema 校验通过。 |
| 关联代码/文档 | 正式来源为 Recovery 基线中的 `docs/platform/24_AI-CS_Customer_Feedback_Loop_V1_Report.md`、`frontend/src/api/aiInteractionEventClient.ts`、`frontend/src/views/AiChat.vue`、`platform_backend/app/customer_feedback_loop/`、`platform_backend/migrations/versions/0008_customer_feedback_loop_v1.py`、`admin_web/src/views/AiIssueCenterView.vue`、`contracts/schemas/ai-interaction-event-*.schema.json`、`contracts/compatibility/customer-feedback-loop-v1.md`。 |
| 防止重复错误规则 | 不得再次把“客服行为没有保存”作为全新需求；如真实运行失败，应登记 R002 的回归或运行缺陷。不得再用浏览器内存、本地成功提示或 Mock 代替 C 的权威回执。 |

### R003 — C新增店铺/商品无法进入B客服

| 字段 | 内容 |
| --- | --- |
| 需求 ID | R003 |
| 提出时间 | 2026-07-29 |
| 需求名称 | C新增店铺/商品无法进入B客服 |
| 用户原始目标 | C 运营创建的数据可以被客服使用。 |
| 业务背景 | 当前 C 可以新增店铺和商品，但 B 无法消费。根因不是页面展示不足，而是缺少业务可用状态以及 B/C 数据激活规则。 |
| 当前状态 | `IN_PROGRESS` |
| 负责模块 | Control / Interface Owner：边界和 Gate；C：业务数据所有者与 Provider；B：Consumer；A：在“AI使用”阶段做下游可用性验证。 |
| 影响范围 | 店铺、商品、SKU从 C 创建到客服可用确认、B 显示和 AI 使用的激活链路；可能影响 C/B接口和运行数据，不授权 Master Data 重构。 |
| 完成标准 | 目标链路真实成立：`C创建 → 客服可用确认 → B显示 → AI使用`；未确认数据不进入 B；B 不自行猜测 C 数据可信度；失败和未激活状态可被明确识别。 |
| 验收证据 | 尚无关闭证据。R006 V1.1静态验证得到`PASS=6`、`CONDITIONAL PASS=3`、`FAIL=0`，但发现旧表同时包含`IMPORTED_TEST_ONLY`与`MANUAL_CREATED`且receipt响应/复核仍不完整；没有实现或运行验收。 |
| 关联代码/文档 | [Pilot Business Catalog Interface Freeze Plan V1](interfaces/AI-CS-Pilot-Business-Catalog-Interface-Freeze-Plan-V1.md)、[Interface Validation Report V1](interfaces/AI-CS-Pilot-Business-Catalog-Interface-Validation-Report-V1.md)、[Interface Freeze Plan V1.1](interfaces/AI-CS-Pilot-Business-Catalog-Interface-Freeze-Plan-V1.1.md)、[Interface Validation Report V1.1](interfaces/AI-CS-Pilot-Business-Catalog-Interface-Validation-Report-V1.1.md)；关联交付需求R006。 |
| 防止重复错误规则 | 不得通过修改 UI、增加前端判断或复用测试字段掩盖数据激活缺口；不得把同一问题另开“B读取C商品”重复需求。问题状态由 R003跟踪，解决方案只进入 R006。 |

### R004 — AI-CS运行版本统一

| 字段 | 内容 |
| --- | --- |
| 需求 ID | R004 |
| 提出时间 | 2026-07-29 |
| 需求名称 | AI-CS运行版本统一 |
| 用户原始目标 | 统一 B、C、A 的运行来源，让已完成能力形成可复现正式基线。 |
| 业务背景 | 当前多个 Worktree 位于不同 branch/commit，并存在未提交修改；C Worktree 同时承载 C、B 和 contracts 改动。运行中的服务与未来开发来源无法被单一 commit 复现。 |
| 当前状态 | `DONE` |
| 负责模块 | Control：恢复顺序与统一基线；各 A/B/C 所有者：按路径拆分正式能力；OPS：运行来源核对；contracts：版本、schema、changelog 和兼容说明收敛。 |
| 影响范围 | A/B/C/Control Worktree、commit、运行来源、共享 contracts 和 Pilot 可复现性；不修改任何业务逻辑、UI、接口或数据库。 |
| 完成标准 | R001 与 R002形成边界清晰的独立 commit；跨线文件按所有权归位；A/B/C/Control 基于批准的同一开发基线；共享 contracts 使用唯一版本且内容一致；目标 Worktree 无未归属脏修改；运行来源可由 branch/commit/目录清单复现。 |
| 验收证据 | Recovery 分支 `control/pilot-baseline-recovery-v1` 从 `develop@671c9a293f1e5e0f462522ad2c7e114c7919c388` 建立；六个能力/契约提交按边界完成；contracts 统一为 `0.2.0`；A `101 passed / 3 skipped`、C `95 passed`、B `115 passed`、Admin `54 passed`；5173/5174/8000/8011 已从同一 clean Recovery SHA 运行并返回 HTTP 200。 |
| 关联代码/文档 | [Baseline Inventory Report](AI-CS-Pilot-Baseline-Inventory-Report-V1.md)、[Baseline Recovery Execution Report](AI-CS-Pilot-Baseline-Recovery-Execution-Report-V1.md)、`docs/control/AI-CS-Pilot-Baseline-V1.machine-context.json`。 |
| 防止重复错误规则 | 以后任何开发前必须确认来源目录、branch、commit、contracts 版本和工作区清洁度。不得在多个 Worktree继续产生无法合并的脏修改，不得以重启服务代替版本收敛。 |

### R005 — Customer Feedback Loop真实运行验证

| 字段 | 内容 |
| --- | --- |
| 需求 ID | R005 |
| 提出时间 | 2026-07-29 |
| 需求名称 | Customer Feedback Loop真实运行验证 |
| 用户原始目标 | 真实客服使用后验证“反馈 → 知识优化 → AI改善”。 |
| 业务背景 | R002 已完成工程实现和隔离自动化验收，但真实客服是否会正确反馈、运营是否能补充知识、AI回答是否实际改善，仍需要 Pilot 运行证据。 |
| 当前状态 | `TODO` |
| 负责模块 | Control / Pilot Owner：验收口径；OPS：受控运行；QA：证据复核；B/C/A：真实链路参与。 |
| 影响范围 | Pilot 使用流程、去标识化反馈样本、C 知识优化处理、A 回答复验和运行证据；不授权自动训练、自动发布或真实客户数据扩张。 |
| 完成标准 | 至少使用获准的真实客服操作完成可追溯闭环；同一问题从反馈进入知识优化，再以人工重新提问验证 AI 是否改善；失败、未改善和安全边界均被如实记录。 |
| 验收证据 | 尚无。R002 的合成数据自动化测试只证明工程链路可用，不能替代本需求的真实 Pilot 验收。 |
| 关联代码/文档 | R002；[客服试运行规范](pilot/客服试运行规范.md)、[数据采集标准](pilot/数据采集标准.md)、[每日检查表](pilot/每日检查表.md)。 |
| 防止重复错误规则 | 不得把 R002 的单元测试、隔离 E2E 或页面演示重复包装成真实运行验证；不得为了“验证改善”自动改 Prompt、自动发知识或伪造改善结果。 |

### R006 — Pilot Business Data Activation V1

| 字段 | 内容 |
| --- | --- |
| 需求 ID | R006 |
| 提出时间 | 2026-07-29 |
| 需求名称 | Pilot Business Data Activation V1 |
| 用户原始目标 | 解决 C Provider 到 B Consumer 的业务数据激活，使已确认可用的店铺、商品和 SKU 可以被客服使用。 |
| 业务背景 | R003 已确认 C 创建能力与 B 消费能力之间缺少正式激活语义。原 V1 兼容方案需要自动筛选旧数据，可能误启用或遗漏历史对象；V1.1 改为运营可控兼容模式。该需求是 R003 的交付任务，不是新的 Master Data 项目。 |
| 当前状态 | `TODO` |
| 负责模块 | Control / Interface Owner：冻结所有权、状态、路径和兼容性；C：Provider 与客服可用状态权威；B：Consumer；A：不修改，后续只验证既有请求可以使用同一激活范围。 |
| 影响范围 | Store/Product客服状态、SKU继承、历史TEST初始化、新PILOT默认值、C运营启停入口、activation receipt、C→B消费和AI下游使用；明确禁止Master Data重构。 |
| 完成标准 | 历史有效TEST数据默认ENABLED且运营可关闭；新PILOT Store/Product默认DISABLED且运营可开启；SKU只继承Product；B只消费C最终投影；每次实际状态变化有C权威receipt；单个商品关闭不影响其他商品；安全与回滚证据齐全。 |
| 验收证据 | [Interface Validation Report V1.1](interfaces/AI-CS-Pilot-Business-Catalog-Interface-Validation-Report-V1.1.md)已对9个Case完成代码映射，结果为`6 PASS / 3 CONDITIONAL PASS / 0 FAIL`，总体`CONDITIONAL PASS / R006_IMPLEMENTATION_BLOCKED`。这不是接口、迁移或运行完成证据。 |
| 关联代码/文档 | R003；[Pilot Business Catalog Interface Freeze Plan V1](interfaces/AI-CS-Pilot-Business-Catalog-Interface-Freeze-Plan-V1.md)；[Interface Validation Report V1](interfaces/AI-CS-Pilot-Business-Catalog-Interface-Validation-Report-V1.md)；[Interface Freeze Plan V1.1](interfaces/AI-CS-Pilot-Business-Catalog-Interface-Freeze-Plan-V1.1.md)；[Interface Validation Report V1.1](interfaces/AI-CS-Pilot-Business-Catalog-Interface-Validation-Report-V1.1.md)；基线`ai-cs-pilot-baseline-v1@cbc77ed883cb99e2eff76ccb8eb3193bbddaba38`。 |
| 防止重复错误规则 | 不得恢复“系统根据旧测试字段自动选择可信数据”的方案；不得把全部旧表记录无差别初始化为TEST；不得扩大成Master Data；不得让B判断C数据可信度；不得为SKU增加独立启停；IV11-B01/B02关闭前不得写实现代码。 |

#### R006 增补需求 — Legacy Compatibility Control

原设计中的旧数据自动映射调整为运营可控兼容模式：

1. 历史TEST数据默认`customer_service_status=ENABLED`，保证现有客服Pilot连续性；运营可以关闭并再次开启。
2. C运营新建数据固定为`data_source=PILOT`、`customer_service_status=DISABLED`，必须经运营确认后开启。
3. C店铺和商品列表增加来源、客服状态、最后修改时间、操作人以及启用/禁用入口；只允许最小增量，不重做页面。
4. SKU继承Product状态，不提供独立启停入口。
5. B只消费C最终`customer_service_status`投影，禁止继续判断`test_data_mode`、`production_usable`等旧字段。
6. 每次Store/Product实际状态变化由C生成并保存activation receipt；同状态幂等重放不生成重复状态变化receipt。
7. 验收必须证明旧测试数据继续可用、运营关闭后B不可见、再次开启后B可见、单个商品关闭不影响其他商品。

V1.1验证补充结论：当前旧表混合`IMPORTED_TEST_ONLY`测试包与`MANUAL_CREATED/c-operation-store.v1`运营数据。前者应初始化为`TEST + ENABLED`，后者应初始化为`PILOT + DISABLED`；未知来源必须隔离。该迁移映射以及状态PUT完整response/持久化receipt复核契约尚未冻结，分别登记为IV11-B01、IV11-B02。

### R007 — 网络环境导致客服无法访问5173

| 字段 | 内容 |
| --- | --- |
| 需求 ID | R007 |
| 提出时间 | 2026-07-24（2026-07-29补录） |
| 需求名称 | 网络环境导致客服无法访问5173 |
| 用户原始目标 | 解决局域网内客服终端无法访问 5173 的问题。 |
| 业务背景 | 本机服务可用并不代表公司网络内其他终端可达。当前判断为公司网络隔离、VLAN 或端口策略问题，而不是 AI-CS 页面或业务代码问题。 |
| 当前状态 | `BLOCKED` |
| 负责模块 | OPS 与公司网络管理；Control 记录 Gate。A/B/C 业务代码不是当前负责人。 |
| 影响范围 | 5173 的局域网路由、防火墙、VLAN、端口策略和第二台电脑验收；不影响 AI-CS 业务模型、接口或数据库。 |
| 完成标准 | 在受控网络策略下，指定客服终端能够访问批准的 5173 地址；服务监听、防火墙和路由证据完整；若网络分段不允许访问，形成明确的网络侧处理结论和责任人。 |
| 验收证据 | 尚无关闭证据。既有本机/LAN检查表明应用端可启动并提供 HTTP，但第二台电脑手工验收仍待完成；跨 VLAN/端口不可达应记录为 `NETWORK_SEGMENTED`。 |
| 关联代码/文档 | [控制面状态看板](01_三线状态看板.md)、`scripts/windows/` 下既有 LAN 启停与诊断工具、`docs/control/machine-context.json` 的 LAN 验证记录。 |
| 防止重复错误规则 | 不得把网络隔离重复登记成 B 页面故障，不得通过修改 UI、接口或业务代码规避公司网络策略；只有出现应用监听或代理证据时才转为 AI-CS 代码缺陷。 |

### R008 — AI-CS Project Structure Simplification V1

| 字段 | 内容 |
| --- | --- |
| 需求 ID | R008 |
| 提出时间 | 2026-07-30 |
| 需求名称 | AI-CS Project Structure Simplification V1 / AI-CS Monorepo Consolidation V1 |
| 用户原始目标 | 将当前多Worktree、多目录、多版本开发模式收敛为一个长期维护的AI-CS Monorepo，历史资产可追溯，未来按大版本发布。 |
| 业务背景 | 目前同一Git仓库登记69个Worktree，其中8个dirty、4个detached；A/B/C和Control长期目录、旧运行路径及多份machine-context造成版本、职责和阻塞事实漂移。 |
| 当前状态 | `IN_PROGRESS` |
| 负责模块 | Control：迁移Gate、需求和版本事实；A/B/C：能力与路径归属；OPS：脚本、运行身份和切换；QA：结构、回归和运行等价验收；contracts：迁移期间保持兼容。 |
| 影响范围 | 仓库目录、文档架构、machine-context、Worktree、分支/发布策略、脚本路径、测试与运行来源；不授权业务功能、UI、接口、数据库、RAG、Prompt或模型变更。 |
| 完成标准 | 最终只保留`AI-CS/`一个长期目录；保持`backend/frontend/extension/platform_backend/admin_web/contracts/docs/scripts/tests`核心目录原名；只保留一个活动machine-context；R001–R006成果和Pilot基线不丢失；四服务从同一release SHA运行；旧Worktree只在功能归属、commit、Tag、clean和运行不占用确认后退役。 |
| 验收证据 | [AI-CS Monorepo Source Freeze Report V1](AI-CS-Monorepo-Source-Freeze-Report-V1.md)冻结源码与运行双锚点；[Phase 2A Target Repository Creation Execution Report V1](AI-CS-Phase-2A-Target-Repository-Creation-Execution-Report-V1.md)记录独立clone和GI-01至GI-10全PASS；[Phase B Code Materialization Report V1](AI-CS-Phase-B-Code-Materialization-Report-V1.md)证明Source/Target 542个文件、Tree/manifest零差异；[Phase C Dependency Reproduction Report V1](AI-CS-Phase-C-Dependency-Reproduction-Report-V1.md)证明四组件依赖可安装；[Phase D Target Validation Report V1](AI-CS-Phase-D-Target-Validation-Report-V1.md)记录初次C失败；[Platform Backend Runtime Compatibility Report V1](AI-CS-Platform-Backend-Runtime-Compatibility-Report-V1.md)冻结3.12.13；[Phase D2 C Backend Environment Rebuild Report V1](AI-CS-Phase-D2-C-Backend-Environment-Rebuild-Report-V1.md)记录venv重建；[Phase D Target Validation Retry Report V1](AI-CS-Phase-D-Target-Validation-Retry-Report-V1.md)记录365 passed/3 skipped；[Phase E Runtime Migration Plan V1](AI-CS-Phase-E-Runtime-Migration-Plan-V1.md)冻结蓝绿方案；[Phase E1 Shadow Runtime Execution Report V1](AI-CS-Phase-E1-Shadow-Runtime-Execution-Report-V1.md)记录独立快照、四服务PID/SHA、Admin实际18000/18011路由、浏览器/API验证与Recovery保护PASS。 |
| 关联代码/文档 | [AI-CS Monorepo Migration Plan V1](AI-CS-Monorepo-Migration-Plan-V1.md)、[AI-CS Physical Migration Execution Plan V1](AI-CS-Physical-Migration-Execution-Plan-V1.md)、[Phase 2A Target Repository Creation Execution Report V1](AI-CS-Phase-2A-Target-Repository-Creation-Execution-Report-V1.md)、[Phase B Code Materialization Report V1](AI-CS-Phase-B-Code-Materialization-Report-V1.md)、[Phase C Dependency Reproduction Report V1](AI-CS-Phase-C-Dependency-Reproduction-Report-V1.md)、[Phase D Target Validation Retry Report V1](AI-CS-Phase-D-Target-Validation-Retry-Report-V1.md)、[Phase E Runtime Migration Plan V1](AI-CS-Phase-E-Runtime-Migration-Plan-V1.md)、[Phase E1 Shadow Runtime Execution Report V1](AI-CS-Phase-E1-Shadow-Runtime-Execution-Report-V1.md)、[Source Tree Manifest V1](manifests/AI-CS-Phase-B-Source-Tree-Manifest-V1.md)、[Target Tree Manifest V1](manifests/AI-CS-Phase-B-Target-Tree-Manifest-V1.md)、[Pilot Baseline Recovery Execution Report](AI-CS-Pilot-Baseline-Recovery-Execution-Report-V1.md)、R001–R006。 |
| 防止重复错误规则 | Phase E1已经通过，但不得把影子运行解释为标准端口已切换或R008已完成。E2必须单独授权，先受管停止影子、确认无写入窗口，再复核Recovery最终备份并按受管记录切换；禁止按端口强杀。不得提交`.runtime`/`.venv`、修改冻结Tree/requirements/lockfile、处理Recovery目录或借迁移实施R006。 |

## 7. 历史错误防复发规则

1. 不要重复开发已经完成的模块。先检索需求 ID、验收证据和关联代码；`DONE` 能力只允许登记回归、修复或明确的新目标。
2. 不要在没有确认运行基线时修改代码。开发前必须确认来源目录、branch、commit、contracts 版本、运行进程来源和未提交修改。
3. 不要直接修改 UI 解决数据问题。先确认数据所有者、Provider、Consumer、业务状态和失败语义。
4. 不要让 B 自己判断 C 业务数据可信度。C 是业务数据和客服可用状态的权威，B 只消费明确投影。
5. 不要用测试字段长期代替业务状态。`is_test`、导入批次、前端常量和临时映射都不能替代正式、可审计的客服可用状态。
6. 不要在多个 Worktree 产生无法合并的脏修改。任务开始前划定路径所有权，跨线工作按 A/B/C/contracts 拆分，并形成独立 commit 和明确合并顺序。

补充执行规则：

- 同一业务问题只能有一个主需求 ID；问题记录与交付任务并存时必须互相引用。
- 不得用 Mock、静态演示数据或本地成功提示关闭跨线需求。
- 不得用“代码已存在”证明运行基线统一，也不得用“运行服务正常”证明代码已提交。
- 新字段、新状态、新错误码、新幂等或版本变化必须先经过 Interface Owner 冻结。
- 任何真实客户数据、正式鉴权、自动脱敏或自动业务动作都需要新的治理需求，不得从现有需求中推定授权。

## 8. 当前主阻塞链与下一入口

```text
R004 统一运行版本（DONE）
  ↓ 已完成 Baseline Recovery
R006 Interface Validation V1.1（CONDITIONAL PASS，需求仍为 TODO）
  ↓ 仅关闭 IV11-B01 混合来源映射、IV11-B02 receipt响应/复核
R006 Implementation（两项关闭并明确授权前 BLOCKED）
  ↓ 获得明确授权后才可开发和联调
R003 C数据进入B的业务结果验收（IN_PROGRESS → DONE）
  ↓ 统一基线与真实业务数据可用
R005 Feedback Loop真实运行验证（TODO）
```

R007 是并行的外部网络阻塞，不应通过修改 AI-CS 业务代码处理。

R006交付链的唯一下一入口仍是`AI-CS Pilot Business Catalog Interface Freeze V1.1 Remediation`，只关闭IV11-B01和IV11-B02。不得修改代码、UI、contracts、数据库或运行服务；两项关闭并复核前不得进入Business Data Activation。

R008是与R006并行的项目治理任务。Phase E1已在15173/15174/18000/18011完成独立数据影子运行：四服务同一Target SHA、Admin实际请求18000/18011、A模型与47 chunks、B/C页面均PASS，Recovery标准端口和数据锚点未变化。下一入口只能是用户另行授权的Phase E2标准端口切换与人工无写入窗口；影子PASS不等于已切换Runtime，也不授权停止Recovery。R008不得绕过R006的Interface Gate，也不得把结构迁移结果作为R003/R005业务验收。

最终状态：`SHADOW_RUNTIME_PASS`
