# AI-CS Monorepo Migration Plan V1

> 需求：R008 — AI-CS Project Structure Simplification V1
>
> 新增目标：AI-CS Monorepo Consolidation V1
>
> 计划日期：2026-07-30
>
> 当前实际候选目录：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-r006-interface-validation-v1`
>
> 当前候选分支 / SHA：`control/r006-interface-validation-v1-1@19cc82682074dc0f11096d4191ad8d19a9f0cc0b`
>
> 受保护Pilot基线：`ai-cs-pilot-baseline-v1@cbc77ed883cb99e2eff76ccb8eb3193bbddaba38`
>
> 未来唯一目录：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`
>
> 本轮性质：只规划，不实施迁移
>
> 当前Gate：`MONOREPO_MIGRATION_PLAN_READY / MIGRATION_NOT_AUTHORIZED`

## 0. 执行结论

AI-CS已经具备单仓库代码形态，但物理开发方式仍是多Worktree、多长期分支、多运行来源。R008的目标不是重新开发A/B/C，而是把已经收敛的正式Pilot能力搬到一个长期目录、一个版本事实源和一个运行身份中。

当前推荐源不是一个名为`AI-CS-r006-interface-validation-v1-1`的物理目录：该目录实际不存在。真实候选是`AI-CS-r006-interface-validation-v1`，其分支名称为`control/r006-interface-validation-v1-1`。该工作树clean，当前SHA为`19cc826...`，并且`ai-cs-pilot-baseline-v1`指向的`cbc77ed...`是其祖先。因此迁移必须以“实际目录 + branch + SHA”三项联合身份为准，不能根据文件夹名称猜测版本。

计划开始时Git登记了69个Worktree，其中61个clean、8个dirty、4个detached。本轮按“禁止修改Git历史”将计划保留为7个未提交Control文档，因此当前即时状态为60个clean、9个dirty；新增的1个dirty就是本候选的已知规划文档，不是业务代码。最终目标是只保留`AI-CS/`一个长期工作目录；但不能直接批量删除。8个既有dirty Worktree必须先完成功能归属、commit可达性、敏感数据和历史Tag检查，本候选规划文档则由后续明确授权决定如何归档。

推荐采用七阶段迁移：源基线冻结 → 创建隔离目标目录 → 纯目录重排 → 路径与脚本适配 → 全量测试和隔离运行等价验证 → 受控Pilot切换 → Worktree退役与`v1.0`发布。任何Gate失败都回到旧目录和已验证Tag，不在失败状态下清理旧资产。

## 1. R008任务卡

| 字段 | 内容 |
| --- | --- |
| 目标 | 将A、B、C、contracts、文档、OPS和测试收敛到唯一长期目录`AI-CS/`，且R001–R006能力、contracts 0.2.0和当前Pilot可复现性不丢失。 |
| 可观察结果 | 开发、测试、发布和四服务运行都能从同一repository root、release tag和SHA说明；旧长期Worktree完成受控退役。 |
| 范围 | 目录迁移规划、文档架构、machine-context治理、Worktree退役规则、Git发布策略、迁移测试与回滚Gate。 |
| 不包含 | 本轮不移动文件、不删除目录、不改代码、不改UI、不改接口、不改数据库、不改contracts、不改Git历史、不重启或切换Pilot。 |
| Owner | Control：迁移Gate与版本；A/B/C：路径归属确认；OPS：脚本与运行切换；QA：回归与等价验收；Data/Privacy：非Git资产边界。 |
| 成功标准 | 唯一目录、唯一活动machine-context、唯一release SHA；R001–R006证据可追溯；四服务同SHA运行；工作树clean；旧目录仅在归属/commit/Tag确认后退役。 |
| 停止条件 | 任一正式能力只存在于未提交工作树、迁移后测试不等价、运行来源无法确认、发现敏感/运行数据将进入Git，或Pilot当前正在使用待删除目录。 |

## 2. 当前项目资产映射

### 2.1 推荐源身份

| 项目 | 当前事实 | 迁移判断 |
| --- | --- | --- |
| 用户描述候选 | `AI-CS-r006-interface-validation-v1-1` | 物理目录不存在，不能作为命令目标。 |
| 实际候选 | `AI-CS-r006-interface-validation-v1` | 推荐作为迁移源；branch为`control/r006-interface-validation-v1-1`。 |
| 候选SHA | `19cc82682074dc0f11096d4191ad8d19a9f0cc0b` | 任务开始时clean；当前只含本轮7个未提交Control文档，HEAD未变化；包含R006 V1.1验证控制证据。 |
| 正式Pilot基线 | `ai-cs-pilot-baseline-v1` → `cbc77ed883cb99e2eff76ccb8eb3193bbddaba38` | 是候选SHA的祖先；必须作为回滚点保留。 |
| contracts | `contracts/version.json = 0.2.0` | 迁移期间保持不变，不借目录迁移升级接口。 |
| R008 Phase 0专用资产地图 | 当前候选中未发现名为`AI-CS Current Project Structure Inventory V1`的tracked文档 | Phase 1必须从本计划记录的只读事实生成并冻结迁移清单，不能假设缺失文档已经入库。 |

### 2.2 当前仓库内资产

| 当前路径 | 所有权 / 用途 | 当前tracked文件数 | 目标归属 |
| --- | --- | ---: | --- |
| `frontend/` | B客服工作台，5173 | 79 | `apps/customer-client/` |
| `extension/` | B浏览器扩展占位/历史资产 | 1 | 先归属确认；保留时进入`apps/customer-client/extension/`，废弃时进入`archive/code/browser-extension/` |
| `admin_web/` | C运营前端，5174 | 74 | `apps/admin-console/` |
| `backend/` | A AI能力层，8000 | 40 | `apps/ai-service/` |
| `platform_backend/` | C运营后端，8011 | 97 | `services/platform-api/` |
| `contracts/` | A/B/C共享契约 | 13 | 原路径保留`contracts/` |
| `docs/` | Control、A/B/C、架构、计划与决策 | 155 | 按第4节收敛，根目录仍为`docs/` |
| `scripts/` | 启停、健康、LAN、备份、恢复和Worktree工具 | 56 | 保留`scripts/`根；路径适配后废弃长期Worktree脚本 |
| `tests/` | 当前只有contract/e2e说明；模块测试仍在各应用内 | 2 | `tests/contracts/`、`tests/integration/`、`tests/e2e/`、`tests/runtime/` |
| `.agents/`、`AGENTS.md` | Agent治理与路径所有权 | 9 + 根文件 | 保留根目录；按新路径更新所有权 |
| `.github/` | CI与仓库治理 | 5 | 保留根目录；改为单仓库发布Gate |
| `logs/README.md` | 日志边界说明，不是运行日志 | 1 | 规则并入`docs/architecture/runtime-data-boundary.md`；实际日志只进`.runtime/` |

### 2.3 仓库外Worktree资产

计划开始时的只读盘点结果：

- 注册Worktree：69。
- clean：61。
- dirty：8。
- detached：4，其中2个dirty。
- 当前dirty集合包括原Control主目录、`AI-CS-platform-center`、`AI-CS-rag-core`、`AI-CS-user-client`以及若干规划/验证工作树。

本计划写入后，推荐候选因7个Control文档变更成为第9个dirty Worktree，所以交付时即时统计是69个注册、60个clean、9个dirty、4个detached。该变化是遵守“不修改Git历史”的预期结果，必须在Phase 1清单中单独标记为`R008_PLANNING_DOCS`，不能与8个既有脏资产混为一谈。

这些目录不是69份独立产品。它们共享同一Git对象库，但分别检出不同branch/SHA并可能含未提交内容。迁移时只把已经确认的commit历史和正式能力带入新根，不把整目录复制进`archive/`。

### 2.4 正式能力保护清单

| 需求 | 必须保留的能力 | 最低保护证据 |
| --- | --- | --- |
| R001 | C商品知识运营中心V2、知识模板、知识状态、知识缺口 | Recovery能力commit、C/Admin测试与关联文档 |
| R002 | B采用行为、C反馈保存、问题中心和知识优化链路 | Contracts/C/B独立commit、schema与全量测试 |
| R003 | 当前问题状态和未来业务验收入口 | Requirement Registry与R006关联不丢失 |
| R004 | 同SHA Pilot基线、contracts 0.2.0、四服务运行身份 | Tag `ai-cs-pilot-baseline-v1`和Recovery报告 |
| R005 | 真实Pilot验证仍为TODO，不伪装成已完成 | Pilot规范、数据边界与未完成状态 |
| R006 | Interface Freeze V1/V1.1、Validation V1/V1.1和两项P0阻塞 | 四份接口文档、Registry状态和Gate |

## 3. 目标Monorepo结构与目录迁移

### 3.1 目标结构

```text
AI-CS/
├── apps/
│   ├── customer-client/        # B客服工作台，5173
│   │   └── extension/          # 仅在确认仍属正式B能力时保留
│   ├── admin-console/          # C运营前端，5174
│   └── ai-service/             # A AI能力层，8000
├── services/
│   └── platform-api/           # C运营后端，8011
├── contracts/                  # A/B/C共享契约
├── docs/                       # 统一文档中心
├── scripts/                    # 启动、停止、状态、健康、备份与恢复
├── tests/
│   ├── contracts/
│   ├── integration/
│   ├── e2e/
│   └── runtime/
├── archive/                    # 退役代码/脚本及其manifest，不保存整仓副本
├── .runtime/                   # 本地状态、日志、PID、DB和运行证据原件；Git忽略
├── .agents/
├── .github/
├── AGENTS.md
├── README.md
└── .gitignore
```

### 3.2 路径迁移矩阵

| 当前路径 | 目标路径 | 迁移方式 | 兼容要求 |
| --- | --- | --- | --- |
| `frontend/**` | `apps/customer-client/**` | 在迁移分支使用`git mv` | 保留package lock、Vite配置、测试和5173行为；不得顺便改UI |
| `admin_web/**` | `apps/admin-console/**` | `git mv` | 保留pnpm配置、路由、测试和5174行为 |
| `backend/**` | `apps/ai-service/**` | `git mv` | 保留Python包、迁移前模型/Prompt/RAG逻辑和8000接口 |
| `platform_backend/**` | `services/platform-api/**` | `git mv` | 保留Alembic历史、SQLite兼容、8011接口和C Provider语义 |
| `extension/**` | `apps/customer-client/extension/**`或`archive/code/browser-extension/**` | 先由B Owner确认是否正式能力 | 不允许因只有一个tracked文件就直接删除 |
| `contracts/**` | `contracts/**` | 不移动 | 迁移期固定0.2.0；任何内容变更走独立Interface任务 |
| `tests/contract/**` | `tests/contracts/**` | `git mv` | 同时更新CI路径，不改变schema判定 |
| `tests/e2e/**` | `tests/e2e/**` | 原位扩充 | 只使用合成/去标识化数据 |
| `scripts/windows/**` | `scripts/windows/**` | 原位修改路径解析 | 所有脚本从repository root推导新路径，不保存旧绝对Worktree路径 |
| `logs/README.md` | `docs/architecture/runtime-data-boundary.md` | 合并规则后移除空日志目录 | 实际日志继续只写`.runtime/` |
| 根配置 | 根配置 | 保留并更新相对路径 | 不在迁移中升级依赖或工具链 |

### 3.3 迁移实现边界

未来实施必须把“纯移动”和“行为适配”分成可复核提交：

1. 建立目标骨架与新路径所有权。
2. 只移动B客服代码。
3. 只移动C Admin代码。
4. 只移动A服务代码。
5. 只移动C API代码。
6. 更新脚本、CI、测试和文档引用。
7. 统一machine-context并生成release证据。

禁止在上述提交中混入页面优化、接口字段、数据库模型、依赖升级、Prompt/RAG调整或Business Data Activation。若纯移动后必须修改import、工作目录或静态资源路径，只允许最小路径适配，并要求等价测试证明业务行为未变。

## 4. 文档收敛方案

### 4.1 目标文档架构

```text
docs/
├── control/
│   ├── AI-CS-Requirement-Registry-V1.md
│   ├── machine-context.json
│   ├── interfaces/
│   ├── releases/
│   └── handoff/
├── customer/                   # B客服产品与操作文档
├── platform/                   # C Admin与Platform API文档
├── rag/                        # A AI服务、RAG和质量文档
├── architecture/
│   ├── repository-layout.md
│   ├── runtime-topology.md
│   ├── decisions/
│   └── migration/
└── archive/
    ├── superseded-control/
    ├── line-status-snapshots/
    ├── plans/
    └── release-history/
```

### 4.2 当前文档映射

| 当前目录 | 目标 | 处理规则 |
| --- | --- | --- |
| `docs/control/` | `docs/control/` | 继续作为需求、接口、Gate、发布和交接唯一事实源；R001–R008台账保留活动状态 |
| `docs/customer/` | `docs/customer/` | 保留B业务和运维说明；去除独立Worktree路径与重复状态事实 |
| `docs/platform/` | `docs/platform/` | 同时服务Admin与Platform API，以子目录或索引区分；不复制到两处 |
| `docs/rag/` | `docs/rag/` | 保留A/RAG事实、测试和安全边界；路径更新到`apps/ai-service` |
| `docs/architecture/` | `docs/architecture/` | 作为当前架构事实；合并`docs/decisions/`为`architecture/decisions/` |
| `docs/plans/` | 活跃项进入`docs/architecture/migration/`或对应需求；过期项进入`docs/archive/plans/` | 每份文档必须标记`ACTIVE`、`SUPERSEDED`或`HISTORICAL` |
| 历史状态/交接 | `docs/archive/line-status-snapshots/` | 只保留审计，不再作为当前事实源 |

### 4.3 正式资产与历史资产边界

以下内容即使日期较早，也不得因为“旧文档”而直接归档：Requirement Registry、R001/R002验收证据、R004 Recovery报告、contracts兼容说明、R006冻结与验证文档、当前运行/回滚规则。

只有已经被明确版本替代且不再指导当前实现的状态快照、重复交接、旧执行计划和临时评审报告可以进入`docs/archive/`。归档文档顶部必须写明原路径、归档日期、替代文档和最后适用版本；所有活动文档链接完成替换后才能移动。

根`archive/`用于退役代码、脚本和迁移manifest，不用于复制整个历史仓库。完整代码历史由Git commit和Tag保存，避免在仓库中维护第二份源码。

## 5. machine-context治理

### 5.1 唯一事实源

未来只保留一个活动文件：

```text
docs/control/machine-context.json
```

当前`docs/rag/machine-context.json`、`docs/customer/machine-context.json`和`docs/platform/machine-context.json`包含独立Worktree路径、旧branch及过时contracts描述。迁移时先把仍有效的事实合并到总控文件，再将历史内容改名为日期化context snapshot并放入`docs/archive/line-status-snapshots/`；它们不再叫`machine-context.json`，也不得被Agent当作当前状态读取。

### 5.2 最小Schema

唯一machine-context至少包含：

```json
{
  "project": {
    "id": "ai-cs",
    "repository_root": "<runtime-resolved>",
    "layout_version": "monorepo-v1"
  },
  "release": {
    "version": "v1.0",
    "branch": "main",
    "sha": "<full-sha>",
    "contracts_version": "0.2.0",
    "clean": true
  },
  "requirements": {
    "registry": "docs/control/AI-CS-Requirement-Registry-V1.md",
    "active": ["R003", "R006", "R008"],
    "blockers": []
  },
  "runtime_services": {
    "customer_client": {"path": "apps/customer-client", "port": 5173},
    "admin_console": {"path": "apps/admin-console", "port": 5174},
    "ai_service": {"path": "apps/ai-service", "port": 8000},
    "platform_api": {"path": "services/platform-api", "port": 8011}
  },
  "boundaries": {},
  "prohibitions": [],
  "gates": {},
  "last_updated": "YYYY-MM-DD"
}
```

`repository_root`不得长期写死某台电脑的绝对路径；由脚本运行时解析，release记录只保存相对路径、版本和SHA。禁止把PID、密钥、数据库路径、客户数据、Prompt正文或运行日志写入machine-context。

### 5.3 更新规则

- Requirement Registry是需求事实源；machine-context只引用当前状态，不复制长篇需求说明。
- 发布、运行SHA、阻塞、接口版本或禁止事项变化时，同步更新Registry、状态摘要、看板、变更记录、交接和machine-context。
- CI校验JSON可解析、路径存在、contracts版本一致、活动需求ID在Registry中存在、四个服务路径无旧目录引用。

## 6. Worktree收敛策略

### 6.1 分类

| 类别 | 当前对象 | 当前处理 | 最终处理 |
| --- | --- | --- | --- |
| 迁移源 | `AI-CS-r006-interface-validation-v1@19cc826...` | 保留、只读作为源 | 新`AI-CS/`通过全部Gate后移除旧Worktree目录；branch/commit保留 |
| Pilot回滚 | `AI-CS-pilot-baseline-recovery-v1`及其Tag | 保留到新根完成等价运行和至少一次受控回滚演练 | 物理目录可退役，Tag与Recovery报告永久保留 |
| 既有脏A/B/C/Control工作树 | 计划开始前8个dirty Worktree | 立即标记`QUARANTINED`，禁止删除、强制清理或覆盖 | 每个文件完成归属与commit/归档判断后单独处置 |
| R008规划候选 | 本轮后新增的第9个dirty Worktree，仅7个Control文档 | 保留为已知规划交付，不与业务脏改混合 | 获得下一阶段授权后按用户决定归档，不在本轮commit |
| Clean功能工作树 | 计划开始时61个、交付时60个clean Worktree中的命名分支 | 检查commit是否已合并、被Tag覆盖或明确废弃 | 受控`git worktree remove`，必要时把branch归档到`archive/*`命名或Tag |
| Detached验证工作树 | 当前4个，其中2个dirty | 先确认验证证据和脏内容 | clean且证据已引用后移除；dirty按隔离流程 |
| 非Git运行/备份目录 | `.runtime`、数据库、日志、配置备份、依赖、构建结果 | 不进入仓库archive | 按本地保留策略外部备份或人工删除 |

### 6.2 删除前强制Gate

每个待退役目录必须逐项完成：

1. **功能归属确认**：所有tracked和untracked文件归入R001–R008、明确废弃项或非Git运行资产。
2. **commit确认**：正式代码已存在于候选SHA或获批迁移commit；记录`source_path → commit → target_path`。
3. **历史Tag确认**：至少有可回滚Tag/commit和迁移manifest；Tag必须解引用到预期commit。
4. **敏感边界确认**：`.env`、数据库、日志、知识源、向量、模型、客户数据、配置备份不得因归档进入Git。
5. **运行占用确认**：该目录不是5173/5174/8000/8011当前运行来源，且没有受管进程仍引用它。
6. **清洁确认**：`git status --porcelain`为空；dirty目录不得用`--force`移除。
7. **可达性确认**：分支顶端commit可从保留Tag、保留branch或release manifest定位。

只有七项全部通过，才允许使用Git原生命令移除该精确Worktree。禁止在资源管理器中批量删除、禁止`git worktree remove --force`、禁止在未验证路径上递归删除。随后执行只读清单复核，再使用`git worktree prune`清理失效登记。

### 6.3 archive与delete的含义

- **保留**：当前仍参与迁移、运行或回滚的物理目录。
- **归档**：保留commit/Tag、manifest和必要的非敏感历史说明；不把整份checkout复制到Git的`archive/`。
- **删除**：只删除已确认冗余的物理Worktree检出和登记；不等于删除Git历史。
- branch删除是单独决策，必须在Worktree退役之后进行；本计划不授权删除branch或改写历史。

## 7. Git大版本发布策略

### 7.1 分支模型

长期分支只保留：

- `main`：最新已验收大版本，只接受release合入。
- `feature/Rxxx-short-name`：从最新release Tag创建，需求完成后合入并删除；不是长期A/B/C分支。
- `release/vX.Y`：短期集成与稳定分支，通过Gate后合入`main`并打Tag，随后关闭。

默认在唯一`AI-CS/`目录中串行切换feature branch。确需多Agent并行时，只允许Control登记的短期临时Worktree：必须从同一release SHA创建、限定需求和所有权、不得承担正式运行，并在合入后立即按第6节退役。项目最终态始终只有一个长期目录。

### 7.2 “不频繁上传小修复”的准确规则

- 本地仍使用小而清晰的atomic commit，保证审查和回滚；不得把数周修改压成一个无法审计的巨型提交。
- feature branch达到任务Gate前不要求每次小修复都push；只在协作备份、评审候选和release候选三个节点上传。
- 对外稳定版本按需求批次发布为`v1.0`、`v1.1`、`v1.2`，不为文案、路径或单个小修复频繁升级公开版本。
- 普通修复进入下一大版本批次。只有阻断Pilot或安全问题才允许紧急hotfix，且必须有独立Incident、回归、回滚和明确授权，不能成为日常发布方式。

### 7.3 每个版本的强制内容

每个`vX.Y`必须同时冻结：

1. 代码SHA与完整目录manifest。
2. contracts版本、schema校验、changelog和兼容说明。
3. Requirement Registry状态与本版本需求清单。
4. A、B、C Admin、C API和集成测试结果。
5. 四服务运行身份：repository root、branch/tag、SHA、clean、端口和health。
6. 安全边界与禁止事项。
7. 回滚Tag、数据备份要求和回滚步骤。

建议版本证据路径：

```text
docs/control/releases/v1.0/
├── release-manifest.md
├── requirements.md
├── test-results.md
├── runtime-verification.md
└── rollback.md
```

运行原始日志、PID、数据库和配置仍只保存在Git忽略的`.runtime/`；Git内`runtime-verification.md`只能记录脱敏结果、SHA和Gate，不得嵌入原始运行数据。

## 8. 未来开发规则

```text
提出需求
  ↓
Requirement Registry检索与登记
  ↓
确认最新release Tag、machine-context和运行来源
  ↓
创建feature/Rxxx-*分支
  ↓
需要跨线字段时先Interface Freeze
  ↓
按新路径所有权开发
  ↓
模块测试 + contracts + 集成/E2E + 安全检查
  ↓
合入release/vX.Y候选
  ↓
四服务同SHA隔离验收
  ↓
合入main并打vX.Y Tag
  ↓
受控运行切换与回滚验证
  ↓
验收证据回写Registry并关闭需求
```

未来所有Agent必须先读根`AGENTS.md`、Requirement Registry、唯一machine-context和其负责模块文档。路径所有权调整为：

- B：`apps/customer-client/**`、`docs/customer/**`。
- C Admin：`apps/admin-console/**`；C API：`services/platform-api/**`；共同文档为`docs/platform/**`。
- A：`apps/ai-service/**`、`docs/rag/**`。
- Shared：`contracts/**`、`tests/**`、`scripts/**`、`docs/control/**`、`docs/architecture/**`，必须由对应Owner与Control共同复核。

同一需求只允许一个主feature branch；禁止重新建立长期`agent/rag-core`、`agent/user-client`、`agent/platform-center`式分支和目录。跨线能力通过contracts和集成测试协作，不通过复制另一线路代码或直接访问私有实现。

## 9. 风险分析与控制

| 风险 | 等级 | 影响 | 控制措施 |
| --- | --- | --- | --- |
| 丢失R001–R006成果 | P0 | 已完成能力被覆盖或误归档 | 迁移前建立需求→源commit→源路径→目标路径manifest；逐项运行既有验收 |
| dirty Worktree被删除 | P0 | 未提交正式能力永久丢失 | 8个既有dirty目录全部隔离；R008规划候选单独保留；归属/commit/Tag未完成前禁止删除或force |
| Pilot运行引用旧绝对路径 | P0 | 切换或删除后服务不可启动 | OPS先读取受管运行记录；新根隔离验证通过前不停止旧Pilot、不删旧根 |
| 脚本路径失效 | P0 | 启停、状态、备份和恢复失效 | 所有脚本从Git root解析相对路径；执行脚本单测、safe stop/restart和rollback演练 |
| Alembic/SQLite工作目录变化 | P0 | 数据库定位错误或误迁移 | 不改migration内容；使用隔离数据库完成upgrade/downgrade/upgrade和路径验证 |
| Git history难追踪 | P1 | 文件移动后难以审计来源 | 使用`git mv`、分模块提交和source-target manifest；禁止复制后删除的无历史搬法 |
| 大版本策略掩盖变更 | P1 | 一个版本混入过多不可回滚修改 | 本地atomic commit + 单需求Gate + release manifest；“少发布”不等于“少记录” |
| archive混入敏感数据 | P0 | 密钥、客户数据、知识和日志泄漏 | archive只接受tracked代码/文档和脱敏manifest；非Git资产始终留在`.runtime`或外部受控备份 |
| 多份machine-context继续漂移 | P1 | Agent依据旧路径/版本开发 | 只保留一个活动context；CI拒绝新增第二个`machine-context.json` |
| R006被目录迁移夹带实施 | P0 | 绕过Interface Gate改变业务 | R006保持`R006_IMPLEMENTATION_BLOCKED`；迁移分支不得修改contracts、接口、业务字段或数据库 |
| R007网络问题被误归因 | P1 | 用业务代码修网络 | 网络Gate独立；Monorepo运行成功不等于第二终端可达 |

## 10. 分阶段迁移与Gate

### Phase 0 — Plan（本轮）

- 只读确认候选、Tag祖先、目录资产和Worktree数量。
- 生成本计划并登记R008。
- 不移动、不删除、不提交、不重启。

Gate：`MONOREPO_MIGRATION_PLAN_READY`。

### Phase 1 — Source Freeze

- 生成逐Worktree清单：路径、branch、SHA、clean、所有权、是否被Tag/合并覆盖。
- 对8个既有dirty Worktree逐文件分类，并单独登记本轮R008规划文档，但不自动提交。
- 冻结`source_path → source_commit → target_path → requirement_id`迁移manifest。
- 经授权创建`ai-cs-monorepo-pre-migration-v1`保护Tag；确认`ai-cs-pilot-baseline-v1`仍可解引用。
- 确认当前四服务实际运行根目录，记录不切换。

Gate：`MONOREPO_SOURCE_FROZEN`。缺少R008 Phase 0资产地图、任何dirty归属不明或运行身份不明时不得进入Phase 2。

### Phase 2 — Isolated Target and Pure Moves

- 从冻结SHA创建短期迁移分支与目标目录`AI-CS/`。
- 按第3节分提交执行纯`git mv`。
- 不复制`.runtime`、依赖、日志、数据库、知识、向量或模型。
- 暂时保留旧候选与Pilot目录作为回滚，不清理Worktree。

Gate：`MONOREPO_STRUCTURE_MAPPED`。

### Phase 3 — Path Adaptation and Static Verification

- 最小更新import、配置、脚本、CI、文档和测试路径。
- 保持contracts 0.2.0、数据库schema、端口、接口、UI、Prompt、模型和业务逻辑不变。
- 检查旧绝对目录名和旧活动machine-context引用为零。

Gate：`MONOREPO_STATIC_PARITY_PASS`。

### Phase 4 — Full Test and Isolated Runtime Parity

- A全量pytest；C API全量pytest与Alembic往返；B/Admin typecheck、全量测试和build。
- contracts schema、OPS脚本、根integration/e2e和敏感文件检查通过。
- 使用隔离数据库、运行状态和非正式端口完成四服务同SHA验证；不影响现有Pilot。
- 对R001、R002和R006当前未实施边界执行回归，确认R003/R005/R006/R007状态未被伪造关闭。

Gate：`MONOREPO_RUNTIME_PARITY_PASS`。

### Phase 5 — Controlled Pilot Switch

- 选择明确无人使用的维护窗口。
- 先生成可恢复备份并验证旧Pilot安全停止条件。
- 从`AI-CS/`同一clean SHA启动5173、5174、8000、8011，验证health、固定代理、目录、真实受控AI smoke和Feedback Loop。
- 若任一项失败，停止新根并恢复`ai-cs-pilot-baseline-v1`或迁移前Tag；不删除旧目录。

Gate：`SINGLE_MONOREPO_RUNTIME_READY`。

### Phase 6 — Worktree Retirement

- 先处理clean且已被保留commit/Tag覆盖的Worktree。
- dirty、detached和运行相关目录逐个通过第6.2节七项Gate。
- 最终`git worktree list`只保留`AI-CS/`；旧分支是否删除另行审批。

Gate：`WORKTREE_CONSOLIDATION_COMPLETE`。

### Phase 7 — v1.0 Release

- 生成完整release文档、测试、运行和回滚证据。
- 合入`main`并创建`v1.0`，Tag解引用到唯一验收SHA。
- Requirement Registry将R008改为`DONE`；在此之前始终保持`IN_PROGRESS`。

Gate：`AI_CS_MONOREPO_V1_RELEASED`。

## 11. 验收清单

R008只有同时满足以下条件才能关闭：

- [ ] 物理长期项目目录只有`AI-CS/`。
- [ ] `git worktree list`没有遗留长期A/B/C/Control工作树。
- [ ] `main@v1.0`、contracts 0.2.0和四服务运行SHA一致，工作树clean。
- [ ] R001商品知识V2回归通过。
- [ ] R002 Feedback Loop回归通过。
- [ ] R003、R005、R006、R007状态保持真实，未因迁移被错误关闭。
- [ ] B/Admin/A/Platform API全量测试、build、contracts、integration和runtime Gate通过。
- [ ] 唯一活动`docs/control/machine-context.json`存在且不含旧Worktree绝对路径。
- [ ] Requirement Registry、发布记录、运行验证和回滚文档完整。
- [ ] `.env`、知识源、向量、日志、数据库、模型、依赖、构建物、客户数据和`.runtime`均未进入Git。
- [ ] 所有删除目录都有功能归属、commit、Tag、clean和运行不占用证据。

## 12. 本轮未执行事项

本轮没有移动或删除任何文件/目录，没有改名`AI-CS-r006-interface-validation-v1`，没有创建`AI-CS/`，没有修改业务代码、UI、接口、contracts、数据库或运行数据，没有重启/停止服务，没有创建/删除branch或Tag，没有commit、push、merge、rebase或改写Git历史。

下一入口只能是R008 Phase 1 `Monorepo Source Freeze`。该阶段仍以盘点、归属和保护Tag审批为主；在`MONOREPO_SOURCE_FROZEN`前不允许执行目录迁移。

最终状态：`MONOREPO_MIGRATION_PLAN_READY`
