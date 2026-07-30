# AI-CS Physical Migration Execution Plan V1

> 需求：R008 AI-CS Project Structure Simplification V1
>
> 阶段：Phase 2 — Physical Migration Preparation
>
> 文档状态：`ACTIVE / EXECUTION_NOT_AUTHORIZED`
>
> 日期：2026-07-30
>
> 唯一代码来源：`ai-cs-monorepo-source-freeze-v1`
>
> 当前运行/回滚锚点：`ai-cs-pilot-baseline-v1@cbc77ed883cb99e2eff76ccb8eb3193bbddaba38`

## 0. 计划结论

本计划把Physical Migration拆成可停止、可验证、可回滚的六个执行阶段。核心代码目录保持原名，不再按此前规划重命名为`apps/**`或`services/**`；这避免为了结构美观改变import、脚本、构建、运行工作目录和既有功能。

本轮只生成执行计划和同步Control治理状态，没有执行任何迁移动作：

- 没有创建`AI-CS/`；
- 没有复制、移动、删除文件或Worktree；
- 没有安装依赖；
- 没有修改代码、UI、contracts、数据库、业务数据、知识、向量或运行配置；
- 没有停止、重启或切换5173、5174、8000、8011。

本计划完成后的Gate是：

```text
PHYSICAL_MIGRATION_PLAN_READY
EXECUTION_REQUIRES_EXPLICIT_AUTHORIZATION
```

## 1. R008 Phase 2任务卡

| 字段 | 内容 |
| --- | --- |
| 目标 | 为未来创建唯一长期维护目录`AI-CS/`提供逐阶段、可验证、可回滚的执行程序，同时保持Pilot连续和R001–R006能力完整。 |
| 当前范围 | 仅`docs/control/**`治理文档；定义目标结构、来源、验收、数据边界、执行阶段、回滚和Gate。 |
| 当前不包含 | 创建目标目录、代码物化、依赖安装、测试执行、运行切换、旧目录归档或Worktree退役。 |
| Owner | Control：Gate与证据；OPS：依赖/运行/数据保护；A/B/C：功能验收；QA：测试、浏览器与迁移等价复核。 |
| 成功标准 | 迁移执行人可仅凭本计划确认唯一来源、准确目录、命令边界、功能清单、失败停止点、运行切换条件和回滚锚点。 |
| 停止条件 | 来源Tag不匹配、目标目录已存在、任一源/运行锚点不clean、数据路径不明确、测试失败、服务身份不明、数据库revision或数量漂移。 |

## 2. 目标目录结构确认

### 2.1 最终结构

```text
AI-CS/
├── backend/                   # A AI能力层，8000
├── frontend/                  # B客服工作台，5173
├── extension/                 # B浏览器扩展资产；保持现状，不在迁移中删除
├── platform_backend/          # C运营后端，8011
├── admin_web/                 # C运营前端，5174
├── contracts/                 # A/B/C共享契约，保持0.2.0
├── docs/                      # 统一文档中心
├── scripts/                   # 启动、停止、状态、健康、备份与恢复
├── tests/                     # contracts、integration和e2e入口
├── archive/                   # 只保存非敏感manifest/退役说明，不复制整仓或运行数据
├── .runtime/                  # 本地运行状态，Git忽略；不从旧目录复制
├── .agents/
├── .github/
├── AGENTS.md
├── README.md
├── CONTRIBUTING.md
├── .gitignore
└── 其他冻结Tag中已跟踪的根配置
```

### 2.2 目录裁决

| 冻结源路径 | 目标路径 | Phase 2处理 |
| --- | --- | --- |
| `backend/**` | `backend/**` | 原路径物化，不改名、不改内容 |
| `frontend/**` | `frontend/**` | 原路径物化，不改名、不改UI |
| `extension/**` | `extension/**` | 原路径物化，不因当前内容较少而删除 |
| `platform_backend/**` | `platform_backend/**` | 原路径物化，不改schema或Alembic历史 |
| `admin_web/**` | `admin_web/**` | 原路径物化，不改名、不改UI |
| `contracts/**` | `contracts/**` | 原路径物化，版本保持`0.2.0`，内容零修改 |
| `docs/**` | `docs/**` | 原路径物化；迁移证据只允许后续独立写入`docs/control/**` |
| `scripts/**` | `scripts/**` | 原路径物化；本轮不改路径解析或运行行为 |
| `tests/**` | `tests/**` | 原路径物化；不重命名`contract`或`e2e` |
| `archive/` | `archive/` | 冻结源当前不存在；执行阶段只允许新增规则README和脱敏manifest |
| `.runtime/` | `.runtime/` | 冻结源不跟踪；仅在目标本地生成空的Git忽略运行根，禁止复制旧内容 |
| `logs/README.md` | 原样保留到单独文档治理任务 | 冻结Tag内是tracked边界说明；不复制任何实际日志，不在纯迁移中删除 |

本节取代[AI-CS Monorepo Migration Plan V1](AI-CS-Monorepo-Migration-Plan-V1.md)中将核心代码移动到`apps/**`和`services/**`的目标结构。旧文档继续作为历史决策记录，但Physical Migration必须执行本计划的“原目录名保留”方案。

### 2.3 禁止的结构性扩张

- 禁止为了美观把核心代码目录重命名、嵌套或合并。
- 禁止顺便统一包管理器、Python版本、Node版本、构建工具或依赖版本。
- 禁止移动A/B/C内部模块、改import、改路由、改API base URL或改端口。
- 禁止把旧Worktree、整个仓库副本、数据库、日志或向量复制到`archive/`。
- 禁止把`.runtime/`加入Git；目录内只能出现后续运行阶段生成的本地状态。

## 3. 唯一迁移来源

### 3.1 Source Protection Reference

| 属性 | 冻结值 |
| --- | --- |
| 唯一来源Tag | `ai-cs-monorepo-source-freeze-v1` |
| Tag类型 | annotated tag |
| Tag object | `6b9ba42e93941b3377eb8b9c4f3ec185f771625f` |
| 解引用commit | `26f8cde1e8f7373315baa1ac68d02f7823b4de82` |
| 直接父commit | `19cc82682074dc0f11096d4191ad8d19a9f0cc0b` |
| contracts | `0.2.0` |
| 当前物理对象库入口 | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-r006-interface-validation-v1`；只作为Git对象来源，不作为文件复制源 |

执行前必须同时通过：

1. `git rev-parse ai-cs-monorepo-source-freeze-v1^{commit}`严格等于`26f8cde...`。
2. Tag目标的父提交严格等于`19cc826...`。
3. Tag签出树包含`backend/frontend/extension/platform_backend/admin_web/contracts/docs/scripts/tests`。
4. `contracts/version.json`仍为`0.2.0`。
5. 源码保护Tag和运行Tag都可解引用；当前运行根仍clean。
6. 目标绝对路径解析后严格等于批准的`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`且尚不存在。

任一项不满足，Phase A不得开始。

### 3.2 禁止的来源方式

- 禁止使用`Copy-Item`、资源管理器、`robocopy`或压缩包从任一Worktree复制代码。
- 禁止从8个dirty Worktree、4个detached Worktree或当前branch HEAD直接取工作区文件。
- 禁止把未跟踪文件、依赖、构建产物或运行数据解释为“缺失代码”并补入目标。
- 禁止使用分支名、短SHA或目录名代替保护Tag校验。
- 禁止移动现有源码Worktree来冒充新主目录。

### 3.3 计划的安全物化方式

执行阶段使用Git对象而不是工作区复制：

1. 通过本地Git对象库执行`clone --no-hardlinks --no-checkout`创建独立目标仓库；Phase A不签出工作树。
2. 在目标仓库显式从`ai-cs-monorepo-source-freeze-v1`创建短期迁移分支。
3. 签出后立即比较Tag tree、tracked文件清单、文件mode和contracts版本。
4. 后续结构证据只形成新的治理commit；业务代码仍必须与来源Tag零差异。

这样即使源Worktree存在未提交文件，Git也不会把它们带入目标。禁止使用本地硬链接，避免源仓库退役影响目标对象完整性。

## 4. 功能保护验收清单

功能保护必须经过“入口存在 → 自动化回归 → 隔离运行 → 人工业务核验”四层证据。仅页面HTTP 200或文件存在不能判定能力完整。

### 4.1 B — 客服工作台

| 必保能力 | 冻结入口 | 自动化/运行验收 | 失败判定 |
| --- | --- | --- | --- |
| 客服聊天 | `frontend/src/views/AiChat.vue`及目录client/adapter | 5173可打开；店铺→商品→SKU选择、提问、清空/下一条咨询、错误状态保持 | 页面缺失、级联错误、异常被显示为“暂无数据” |
| AI回答 | `frontend/src/api/ragClient.ts`、`ragAdapter.ts`、`ragTypes.ts` | 既有A请求与response adapter回归；受控问题返回答案、来源与人工核对提示 | Mock成功、无来源、自动发送或失败伪装成功 |
| 反馈 | `aiInteractionEvent*`、`aiResponseFeedback*`、`experienceCase*` | 采用/修改后采用/未采用只在C真实receipt后成功；幂等重放不重复创建 | 浏览器本地成功、回执缺失、反馈与案例混用 |

B Gate还必须通过`npm ci`后的typecheck、全量Vitest和production build；不得重新设计客服UI。

### 4.2 C — 运营中心与Platform API

| 必保能力 | 冻结入口 | 自动化/运行验收 | 失败判定 |
| --- | --- | --- | --- |
| 商品知识中心 | `product_knowledge/`、`knowledge_materials/`、`KnowledgeCenterView.vue`、`KnowledgeEditorView.vue` | 店铺→商品→SKU知识、模板、知识状态与来源可读 | 结构丢失、模板缺失、状态混为一类 |
| 商品维护 | `operation_management/`、`StoreManagementView.vue`、`ProductDetailView.vue` | 现有创建/查看/维护行为保持；不出现R006新字段 | 行为变化或夹带Business Data Activation |
| FAQ | `test_catalog/`、`knowledge_materials/`、知识编辑/只读视图 | FAQ内容、来源、适用范围和人工维护边界不丢失 | 自动发布或FAQ不可访问 |
| 安全规则 | `test_catalog/`、知识编辑及安全规则路由 | 风险、禁止承诺、人工确认、转人工条件保持 | 安全规则缺失或自动执行业务动作 |
| 知识缺口 | `product_knowledge/`、`KnowledgeGapCenterView.vue` | 缺口识别、排序和运营查看保持 | 缺口被空态掩盖或无法按业务对象查看 |
| 导入中心 | `ingestion/`、`ImportCenterView.vue`及tracked模板 | 商品/SKU/FAQ/安全规则模板与人工审核边界完整 | 自动导入正式数据、自动发布知识或模板丢失 |
| AI问题分析 | `customer_feedback_loop/`、`ai_feedback/`、`AiIssueCenterView.vue`、`AiFeedbackOptimizationPoolView.vue` | C权威保存、问题中心、知识任务、分析结果与状态流转保持 | C回执丢失、B本地替代保存、状态流转退化 |

C Gate必须通过Platform Backend全量pytest、隔离临时SQLite的Alembic往返、Admin typecheck/Vitest/build，以及5174/8011真实页面与API核验。

### 4.3 A — AI能力层

| 必保能力 | 冻结入口 | 自动化/运行验收 | 失败判定 |
| --- | --- | --- | --- |
| RAG | `backend/app/service/rag_service.py`、`test_knowledge.py` | 范围过滤、安全回答、拒答、来源证据回归通过 | 跨店/商品污染、拒答退化、来源丢失 |
| 模型调用 | `rag_service.py`、`config/settings.py`、A API routes | 继续使用批准的本机模型配置；受控smoke得到可复核结果 | 模型或Prompt变化、Mock结果、自动训练 |
| 检索 | `vector_store.py`、`document_loader.py`、`/api/retrieval/search` | tenant/store/product/SKU范围与安全规则检索保持 | 空库伪装成功、重建向量、范围泄漏 |

A Gate必须通过全量pytest；真实RAG测试仍按既有显式环境Gate执行。迁移不修改A模型、Prompt、知识或向量。

### 4.4 基线比较值

迁移后的最低等价基线沿用R004证据：

- A：`101 passed / 3 skipped`；
- C Backend：`95 passed`；
- B：`28 files / 115 tests`；
- C Admin：`25 files / 54 tests`；
- contracts：7个schema校验通过；
- Alembic head：`0008_customer_feedback_loop_v1`。

如果测试数量因环境收集差异变化，必须逐项解释新增、缺失或skip原因；不得只比较“退出码为0”。本计划没有重新运行这些测试，以上是未来执行的比较基线。

## 5. 数据库与运行数据保护方案

### 5.1 核心原则

```text
代码迁移 ≠ 业务数据迁移
```

Physical Migration只物化Git跟踪内容。数据库、知识源、向量、日志、PID/运行记录、模型、依赖、构建产物和客户数据均不从旧目录复制到新目录，不进入Git或`archive/`。

强制禁止：

- 重建数据库、清空表、重新初始化Demo数据；
- 对Pilot数据库运行未批准的Alembic upgrade/downgrade；
- 直接复制正在写入的SQLite文件；
- 重新导入知识、重新同步或重建向量来填补路径错误；
- 同时启动旧C API和新C API写同一个SQLite；
- 修改Store/Product/SKU、Feedback Loop或其他业务状态。

### 5.2 迁移前数据证据

在任何运行切换授权前，OPS必须只读记录：

1. 当前数据库实际路径、文件大小和Alembic revision；不得读取或输出客户内容。
2. 使用既有SQLite online backup入口生成可恢复backup receipt；备份留在Git外受控位置。
3. 店铺、商品、SKU、FAQ、安全规则、知识资料、反馈、AI问题和知识任务的脱敏数量/状态汇总。
4. 向量集合名称、记录数量和配置路径的脱敏摘要；不得导出向量或原文。
5. 当前`.runtime`、数据库、向量和运行记录的Owner、保留位置与回滚用途。

### 5.3 目标运行数据策略

- Phase A/B创建的目标`.runtime/`必须为空且Git忽略，不得自动放入旧业务数据。
- Phase D只使用新建的隔离临时SQLite和合成测试数据；测试结束后按受控临时资产规则处置。
- Phase E正式切换前必须明确目标服务如何访问受保护业务数据。若继续引用Recovery根的数据路径，则Recovery根仍是运行依赖，Phase F不得归档或删除它。
- 将业务数据迁移到新的稳定路径属于独立任务，必须单独授权、备份、校验和回滚；不得由本代码迁移计划隐式执行。
- 新C API启动时若配置指向空库、默认库或需要自动建库，立即停止，不得通过初始化继续。

### 5.4 数据验收

运行切换后只读确认：

- Alembic revision仍为`0008_customer_feedback_loop_v1`；
- 上述脱敏数量不下降，关键状态分布无未解释漂移；
- online backup receipt仍可定位；
- 没有新的未批准SQLite、知识副本或向量库被创建；
- Feedback Loop受控写验收仅使用明确批准的去标识化测试记录，并有清理/保留规则。

任一项失败，Runtime Gate为`FAIL`并立即进入回滚，不得重建数据库补救。

## 6. Physical Migration执行步骤

以下阶段必须在独立任务中逐阶段授权。每个阶段完成后保存脱敏证据并等待Gate；不得把A–F一次性批量执行。

### Phase A — 创建目标目录

前置Gate：`SOURCE_FREEZE_CLOSED`。

执行设计：

1. 再次确认目标绝对路径、父目录和`AI-CS/`不存在；发现同名目录立即停止，不覆盖或合并。
2. 再次解析两个保护Tag、源码/运行SHA、源码contracts和两个工作树clean状态。
3. 使用Git本地对象传输创建独立`AI-CS/`仓库，但`--no-checkout`；禁止文件系统复制和硬链接。
4. 确认新仓库`.git`是目标目录自己的Git目录，不再依赖旧主仓库或worktree gitdir。
5. 不创建`.runtime`内容，不安装依赖，不启动服务。

Gate：`TARGET_REPOSITORY_CREATED`。

失败处理：只保留诊断证据；经再次确认精确目标路径后，才可在单独授权下移除未使用的失败目标。旧Pilot不受影响。

### Phase B — 代码物化

前置Gate：`TARGET_REPOSITORY_CREATED`。

执行设计：

1. 在目标仓库从`ai-cs-monorepo-source-freeze-v1`创建短期分支`control/r008-physical-migration-v1`。
2. 签出冻结tree，不从任何工作区补文件。
3. 保持九个核心目录原名；核对tracked路径、文件mode、tree hash、contracts版本和根配置。
4. 新建`archive/README.md`只说明归档边界；创建空且Git忽略的`.runtime/`本地根。两者不得包含业务数据或整仓副本。
5. 生成`source tag → target branch/SHA → tree manifest`的脱敏迁移记录。

Gate：`SOURCE_TREE_MATERIALIZED`。

失败处理：停止后续阶段，不修改源Tag、不触碰运行根；不得从dirty Worktree“补齐”。

### Phase C — 依赖安装

前置Gate：`SOURCE_TREE_MATERIALIZED`。

执行设计：

1. 使用项目批准的Python/Node运行时；记录版本，不升级工具链。
2. A和C Backend分别在目标目录内建立Git忽略的独立虚拟环境，并严格按冻结`requirements.txt`安装。
3. B使用`npm ci`；Admin使用`pnpm install --frozen-lockfile`。禁止重写lockfile。
4. 所有依赖、缓存、构建产物只进入Git忽略路径；安装后`git status`必须仍只包含批准的结构/治理文件。
5. 依赖解析需要修改requirements、package.json或lockfile时，Phase C立即失败；不得现场升级解决。

Gate：`DEPENDENCIES_REPRODUCED`。

### Phase D — 测试

前置Gate：`DEPENDENCIES_REPRODUCED`。

执行设计：

1. contracts：解析`version.json`，校验7个schema、CHANGELOG和compatibility文件完整；内容必须与来源Tag一致。
2. A：执行Backend全量pytest；真实RAG smoke按显式环境Gate使用批准的测试知识，不读写Pilot数据。
3. C API：使用隔离临时SQLite执行全量pytest及Alembic `upgrade → downgrade → upgrade`往返；不得连接Pilot数据库。
4. B：执行typecheck、全量Vitest和production build。
5. C Admin：执行typecheck、全量Vitest和production build。
6. scripts/tests：执行不触碰当前服务的语法、单元、状态解析和健康检查测试；禁止运行正式stop/start。
7. QA按第4节逐项核对功能入口、测试数、skip、警告和输出；生成迁移测试报告。

Gate：`PHYSICAL_MIGRATION_TEST_PASS`。

任一失败不得进入Phase E，也不得修改业务代码“顺手修复”；应登记独立迁移兼容问题并回到来源/Gate复核。

### Phase E — Runtime切换验证

前置Gate：`PHYSICAL_MIGRATION_TEST_PASS`，并需单独的Runtime Switch授权。

执行设计：

1. 先用隔离端口、隔离`.runtime`和隔离临时SQLite验证目标四服务从同一clean target SHA启动；不得占用5173/5174/8000/8011。
2. 完成B/C/A功能清单、固定代理、AI受控smoke、Feedback Loop和数据无自动动作验证。
3. 在明确维护窗口生成SQLite online backup receipt，确认当前服务无活跃使用，并通过可信运行记录安全停止旧服务；禁止按端口强杀。
4. 明确目标服务的数据路径且确认不会创建空库；禁止新旧C API并发写同一数据库。
5. 从目标同一clean SHA按C API → A → B → C Admin顺序启动8011、8000、5173、5174。
6. 核验repository root、branch、full SHA、clean、managed/listener PID、启动时间、可执行路径、四项health与5173固定代理。
7. 完成第4节人工业务验收及第5.4节数据库验收；安全边界必须继续为人工确认、禁止自动发送/退款/业务执行。
8. 保留旧运行根和回滚Tag，不删除任何旧目录。

Gate：`TARGET_RUNTIME_VALIDATED`。

仅HTTP 200、页面可打开或端口监听均不足以通过本Gate。

### Phase F — 旧目录归档

前置Gate：`TARGET_RUNTIME_VALIDATED`、至少一次受控回滚演练通过、明确观察期结束，并需单独的Worktree Retirement授权。

执行设计：

1. “归档”只保存Tag、branch、commit、脱敏manifest和替代路径，不把旧checkout复制进`archive/`。
2. 先处理clean、未运行且已被Tag覆盖的源目录；逐个满足功能归属、commit、Tag、敏感边界、运行不占用、clean、Git可达七项Gate。
3. 8个dirty和4个detached Worktree继续逐个审计；不得批量删除、force-clean或并入目标。
4. Recovery运行根若仍保存或提供数据库、向量、运行记录等目标运行依赖，必须继续原位保留；代码迁移不授权迁走这些数据。
5. 只有目标已经不再依赖旧根、回滚可从Tag和受控数据备份恢复时，才允许单独退役Recovery物理目录。
6. 最后复核`git worktree list`、运行进程路径、Target clean、保护Tag和archive manifest。

Gate：`OLD_DIRECTORY_RETIREMENT_ELIGIBLE`。

Phase F未通过不否定目标代码/运行迁移结果，但R008不得标记`DONE`，也不得宣称“只剩一个长期目录”。

## 7. 回滚方案

### 7.1 回滚锚点

| 类型 | 路径/引用 | 用途 |
| --- | --- | --- |
| 运行物理锚点 | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-pilot-baseline-recovery-v1` | 恢复当前四服务及其受保护运行配置 |
| 运行Git锚点 | `ai-cs-pilot-baseline-v1@cbc77ed883cb99e2eff76ccb8eb3193bbddaba38` | 确认恢复代码身份 |
| 源码锚点 | `ai-cs-monorepo-source-freeze-v1@26f8cde1e8f7373315baa1ac68d02f7823b4de82` | 重新创建干净迁移目标 |
| 数据锚点 | 原位受保护数据库/向量及最新online backup receipt | 保持业务数据连续；不进入Git |

### 7.2 分阶段回滚

| 失败阶段 | 回滚动作 | 禁止动作 |
| --- | --- | --- |
| A/B目标创建或物化失败 | 停止目标处理，保留诊断；经精确路径复核和授权后丢弃失败目标，再从Source Tag重建 | 不动旧Pilot，不从dirty源补文件 |
| C依赖失败 | 保留lock/运行时差异证据，停止；修正环境计划后重新从clean目标开始 | 不改requirements/lockfile，不升级业务依赖 |
| D测试失败 | 保留测试报告，目标保持隔离；登记迁移兼容问题 | 不改业务逻辑、UI、contracts或Pilot数据来让测试通过 |
| E隔离运行失败 | 仅停止有可信记录的目标隔离服务；标准端口旧Pilot保持不变 | 不按端口强杀，不清空数据库/向量 |
| E正式切换失败 | 可信停止目标服务；从Recovery根按C API → A → B → C Admin恢复；复核PID、SHA、health、代理、功能和数据 | 不重建数据库，不盲目Alembic降级，不删除目标证据 |
| F归档资格失败 | 保留旧目录和Tag，R008继续`IN_PROGRESS` | 不force remove、不批量删除、不改写Git历史 |

正式回滚成功标准：四服务重新来自Recovery根`cbc77ed...`且clean，四个listener/record身份一致，HTTP与固定代理通过，目录、受控AI回答、Feedback Loop和数据库revision/脱敏数量恢复到切换前证据。

## 8. 迁移验收Gate

### Gate 1 — SOURCE_IDENTITY_PASS

- [ ] 唯一来源为`ai-cs-monorepo-source-freeze-v1@26f8cde...`。
- [ ] Source Tag父提交、tree、contracts 0.2.0和保护引用校验通过。
- [ ] 没有从dirty/detached Worktree复制文件。

### Gate 2 — CODE_STRUCTURE_PASS

- [ ] 九个核心目录保持原名、tracked文件和mode完整。
- [ ] 核心业务代码相对Source Tag零差异。
- [ ] `archive/`只含批准的README/manifest；`.runtime/`保持Git忽略。
- [ ] 不存在`apps/**`或`services/**`式核心目录重命名。

### Gate 3 — UI_COMPLETE

- [ ] 5173客服聊天、目录选择、AI回答、来源、人工复制、反馈入口完整。
- [ ] 5174商品知识、商品维护、FAQ、安全规则、知识缺口、导入中心、AI问题分析完整。
- [ ] 页面和业务交互与Source Tag等价，没有UI重设计。

### Gate 4 — TEST_PASS

- [ ] A全量pytest达到或解释R004比较基线。
- [ ] C Backend全量pytest和隔离Alembic往返通过。
- [ ] B/Admin typecheck、全量测试、build通过。
- [ ] 7个contracts schema与0.2.0内容一致。
- [ ] scripts/integration/e2e和敏感文件检查通过。

### Gate 5 — FOUR_SERVICES_HEALTHY

- [ ] 5173、5174、8000、8011来自同一目标repository root和clean SHA。
- [ ] managed/listener PID、启动时间、命令路径、端口与运行记录一致。
- [ ] B/Admin页面、A `/api/health`、C `/health`和B固定代理均通过。
- [ ] 功能验收不以HTTP 200代替。

### Gate 6 — DATABASE_NORMAL

- [ ] Pilot数据库未移动、重建、清空或运行未批准migration。
- [ ] Alembic revision保持`0008_customer_feedback_loop_v1`。
- [ ] 脱敏数量/状态无下降或未解释漂移。
- [ ] online backup receipt可用，未创建意外空库。
- [ ] 新旧C API没有并发写同一数据库。

### Gate 7 — ROLLBACK_AND_ARCHIVE_CONTROLLED

- [ ] Recovery运行锚点和Source Tag仍可用。
- [ ] 受控回滚演练通过。
- [ ] 每个旧目录满足七项退役条件；dirty/detached目录仍隔离。
- [ ] archive无数据库、日志、知识、向量、模型、依赖、构建产物或客户数据。

只有Gate 1–6全部通过，才能声明`PHYSICAL_MIGRATION_RUNTIME_READY`；Gate 7和最终单目录状态通过后，R008才可进入Release/关闭评审。

## 9. 执行证据要求

未来每阶段必须把以下脱敏证据写入`docs/control`或release目录：

- Phase A：目标路径、Git独立性、Source/Runtime Tag解析、创建结果。
- Phase B：source/target tree manifest、contracts版本、结构差异。
- Phase C：运行时版本、lockfile未变、依赖安装结果、Git clean状态。
- Phase D：完整命令、测试数量、skip/警告、失败与复核人。
- Phase E：维护窗口、backup receipt标识、运行根/SHA/PID/health、功能与数据验收。
- Phase F：逐目录退役清单、Tag/commit、运行不占用、敏感边界与回滚可达性。

证据中禁止出现密钥、环境变量值、客户内容、知识正文、数据库内容、完整Prompt、向量或原始日志。

## 10. 当前Gate与下一入口

| 项目 | 当前状态 |
| --- | --- |
| Source Freeze Closure | `PASS / SOURCE_FREEZE_CLOSED` |
| Physical Migration计划 | `PASS / PHYSICAL_MIGRATION_PLAN_READY` |
| 目标`AI-CS/` | 不存在，本轮未创建 |
| Physical Migration执行 | 未授权、未执行 |
| Runtime切换 | 未授权、未执行 |
| Worktree退役 | 未授权、未执行 |
| R006 Implementation | 继续被IV11-B01/B02阻塞，不属于本计划 |

下一入口只能是用户明确授权的`R008 Phase 2A — Target Repository Creation`。即使Phase A获批，也不自动授权Phase B–F；每阶段按本计划Gate推进。

最终状态：`PHYSICAL_MIGRATION_PLAN_READY`
