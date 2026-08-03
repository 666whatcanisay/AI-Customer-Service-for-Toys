# AI-CS Phase 4.1 Preflight Gate Report V1

> 报告性质：生产业务验收前置 Gate 只读审计与恢复方案
> 审计日期：2026-08-03（Asia/Shanghai）
> 正式项目：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`
> 本轮边界：未提交代码、未重启服务、未修改数据库、未修改 R006/R009 核心逻辑

## 0. 结论摘要

Phase 4.1 暂时不能直接进入 R003/R005 正式验收。当前四服务、数据库和 RAG 均处于健康运行状态，但正式仓库存在未纳入版本的治理文档，导致运行身份校验中的 `sourceFingerprint=False`。

阻塞并非业务代码或生产数据故障，而是 Git 源码状态与受控 Runtime 身份不完全一致。推荐采用**方案 A：将三份 Phase 4.1 治理文档形成一次严格的 docs-only 提交，并在同一个人工静默窗口内受控重启四服务**。方案 B 的 clean Worktree 不能单独修复当前正式 Runtime 的身份，且会重新引入多工作区治理风险，因此只作为隔离验收的后备方案。

本报告生成后，工作区预计包含三份未跟踪的 `docs/control/**` 文档。只有在后续获得“提交 + 重启”明确授权，并完成方案 A 后，才可宣告生产验收 Runtime Gate 通过。

**本轮状态：`AI_CS_PHASE_4_1_PREFLIGHT_REPORT_READY`**

---

## 1. 当前状态

### 1.1 Git 身份

| 项目 | 实际值 |
|---|---|
| Repository Root | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS` |
| Branch | `release/product-reliability-hardening-v1` |
| HEAD | `bb16b602ac50a6e554f4e3c42fb10692fff4923f` |
| HEAD 提交 | `merge: include C Admin UX polish` |
| Git clean | 否 |
| 已跟踪代码修改 | 0 |
| 已暂存修改 | 0 |
| 当前 Worktree 数量 | 1 |

审计开始时存在两份未跟踪文件：

| 文件 | 大小 | SHA-256 |
|---|---:|---|
| `docs/control/AI-CS_Project_Handover_Report_V1.md` | 33,134 bytes | `56F83585F30DA8326A5DA478132574177E85B2A6865810985D85BC0CACD0AAEF` |
| `docs/control/AI-CS_Phase_4_1_Production_Validation_Plan_V1.md` | 20,847 bytes | `AAADF443F891BE3CB976F9F8937AA259AEDCFA2716D4D1FFC576B34A98D7369A` |

本报告写入后将新增：

- `docs/control/AI-CS_Phase_4_1_Preflight_Gate_Report_V1.md`

三份文件均为治理和验收文档，不属于业务代码、Runtime 配置或生产数据。

### 1.2 Runtime 身份与健康

状态脚本能够正常完成检查，四服务均在运行：

| 服务 | 入口 | 管理 PID | 监听 PID | 健康 | 运行记录 SHA | Source | runtimeMode | networkMode |
|---|---|---:|---:|---|---|---|---|---|
| C Platform API | `127.0.0.1:8011` | 27828 | 20872 | 正常 | `bb16b602ac50` | `DIRTY` | `standard` | `LAN` |
| A AI Service | `127.0.0.1:8000` | 7104 | 32524 | 正常 | `bb16b602ac50` | `DIRTY` | `standard` | `LAN` |
| B Customer Client | `192.168.1.11:5173` | 25296 | 25296 | 正常 | `bb16b602ac50` | `DIRTY` | `standard` | `LAN` |
| C Admin | `127.0.0.1:5174` | 26896 | 28180 | 正常 | `bb16b602ac50` | `DIRTY` | `standard` | `LAN` |

身份校验明细一致为：

```text
repositoryRoot=True
gitSha=True
sourceFingerprint=False
runtimeMode=True
networkModeRecorded=True
```

这说明运行进程确实来自正式 `AI-CS` 目录，运行 SHA 也与当前 HEAD 一致；唯一失败项是工作区源码指纹，因为新增治理文档使工作区不再 clean。

HTTP 只读检查结果：

| 检查 | 结果 |
|---|---|
| C `/health` | HTTP 200 |
| A `/api/health` | HTTP 200 |
| B 页面 | HTTP 200 |
| Admin 页面 | HTTP 200 |
| A 模型 | `qwen3.5:9b`，ready/configured |
| Active collection | `test_knowledge_v031` |
| Active chunks | 56 |

### 1.3 数据库状态

| 项目 | 实际值 |
|---|---|
| 正式数据库 | `.runtime/phase-e/data/standard-platform.sqlite3` |
| Alembic revision | `0012_internal_production_finalization_v1` |
| 业务表数量 | 36 |
| SQLite integrity_check | PASS |
| foreign_key_check | PASS |
| P0/P1/P2 数据质量项 | `0 / 0 / 0` |

关键计数只读基线：

| 对象 | 数量 |
|---|---:|
| Stores | 2 |
| Products | 24 |
| SKUs | 18 |
| FAQs | 16 |
| Knowledge Materials | 1 |
| Activation Receipts | 10 |
| Publication Receipts | 3 |

本轮未执行 migration、未写入业务表、未修改 SQLite/Chroma 数据。

---

## 2. 阻塞原因

### 2.1 直接原因

正式 Runtime 启动时记录了仓库、Git SHA、源码指纹和运行模式。当前运行记录与仓库根目录、HEAD SHA 均一致，但启动后新增了两份治理文档，本报告又会形成第三份治理文档，因此当前工作区状态不再等于运行时记录的 clean 源码快照。

状态脚本据此正确报告：

```text
gitSha=True
sourceFingerprint=False
source=DIRTY
```

不得通过忽略校验、手工改运行记录或伪造 source fingerprint 绕过该 Gate。

### 2.2 非阻塞项

以下项目目前不是阻塞原因：

- 四服务端口和健康检查正常；
- Runtime 的 Repository Root 和 HEAD SHA 正确；
- 数据库 revision、完整性和外键检查正常；
- RAG active collection 正确且包含 56 个 chunks；
- 未发现业务代码、R006/R009 或 Runtime 配置的未提交修改；
- 未发现多个正式 Worktree 并行运行。

### 2.3 Gate 判定

| Gate | 当前结果 | 说明 |
|---|---|---|
| Git clean | FAIL | 三份治理文档尚未形成受控提交 |
| Runtime repository identity | PASS | 四服务均来自正式 AI-CS 根目录 |
| Runtime Git SHA | PASS | 运行记录与当前 HEAD 均为 `bb16b602...` |
| Runtime source fingerprint | FAIL | 工作区 dirty |
| Service health | PASS | 5173/5174/8000/8011 正常 |
| Database health | PASS | revision 0012，完整性正常 |
| RAG/model health | PASS | 56 chunks，模型 ready |

当前总判定：**`PHASE_4_1_EXECUTION_BLOCKED_BY_RUNTIME_SOURCE_IDENTITY`**。

---

## 3. 恢复方案评估与推荐

### 3.1 方案 A：治理文档 docs-only 受控提交

拟纳入同一次提交的文件必须精确限定为：

1. `docs/control/AI-CS_Project_Handover_Report_V1.md`
2. `docs/control/AI-CS_Phase_4_1_Production_Validation_Plan_V1.md`
3. `docs/control/AI-CS_Phase_4_1_Preflight_Gate_Report_V1.md`

不得使用 `git add .`，不得混入 `admin_web/**`、`frontend/**`、`backend/**`、`platform_backend/**`、`contracts/**`、`scripts/**` 或 `.runtime/**`。

影响评估：

| 影响面 | 评估 |
|---|---|
| Runtime | 提交本身会产生新 HEAD；现有进程仍记录旧 SHA，因此提交后到重启前会短暂出现 SHA 不一致。提交和受控重启必须安排在同一个人工静默窗口。 |
| 数据库 | 无 migration、无 schema/data 写入。标准启动时只应确认现有 revision 0012。 |
| 当前服务 | 本轮不影响；正式执行时需要一次短暂停机并按标准脚本重启四服务。 |
| 业务代码 | 零改动。 |
| 治理一致性 | 直接消除 dirty 根因，并保留 Phase 4.1 决策证据。 |
| 长期维护 | 符合单一正式目录、单一 Runtime 来源原则。 |

### 3.2 方案 B：建立 clean 验收 Worktree

可从 `bb16b602...` 创建 clean Worktree，用于隔离的非生产验收。但它不能单独修复当前正式 Runtime：当前四服务的 Repository Root 仍是原 `AI-CS` 目录，源指纹仍针对原目录计算。

影响评估：

| 影响面 | 评估 |
|---|---|
| Runtime | 不切换服务则无法关闭正式 Runtime 身份 Gate；切换服务仍需要重启和新 Runtime 记录。 |
| 数据库 | 共享正式可写数据库会破坏隔离；使用隔离数据库又不能代表正式生产数据闭环。 |
| 当前服务 | 仅创建 Worktree 不影响服务，但也不解决问题；要作为正式来源仍需切换。 |
| 运行资产 | 新 Worktree 默认没有受控 `.runtime` 资产，需要另行准备。 |
| 长期维护 | 重新引入多工作区和多个运行来源，违背 R008 收敛目标。 |

### 3.3 推荐决定

**推荐方案 A。**

理由：

- dirty 内容全部是应保留的正式治理资产；
- 当前没有业务代码或配置混杂；
- 能在一次最小 docs-only 提交后恢复单一、可追踪基线；
- 无需复制生产数据库、Chroma 或 Runtime 配置；
- 符合 R008 已建立的唯一正式项目目录治理原则。

方案 B 仅在三份治理文档无法获准提交、且验收可以明确降级为隔离非生产验证时作为后备方案。它不应作为生产业务闭环验收的首选基线。

---

## 4. 推荐执行步骤

以下步骤是后续获得明确“允许提交、允许重启”授权后的执行方案；**本轮不执行**。

### Step 1：人工静默窗口确认

- 确认当前无客服和运营人员正在执行写操作；
- 明确预计短暂停机窗口；
- 确认 Recovery/回滚入口可用；
- 保留当前 PID、SHA、数据库与 RAG manifest。

### Step 2：提交前精确复核

```powershell
git status --short
git diff --name-status
git diff --cached --name-status
```

验收条件：

- 已跟踪文件无修改；
- 暂存区为空；
- 未跟踪文件仅为上述三份 `docs/control/**` 文档。

### Step 3：仅暂存三份文档

必须使用三个精确文件路径进行 `git add -- <path>`；禁止 `git add .`。

暂存后执行：

```powershell
git diff --cached --name-status
git diff --cached --stat
```

验收条件：暂存内容全部位于 `docs/control/**`，无代码、配置、数据库、运行文件或构建产物。

### Step 4：形成 docs-only 基线提交

建议提交说明：

```text
docs(control): establish phase 4.1 validation baseline
```

提交后记录新 SHA，并立即确认：

```powershell
git status --porcelain
git rev-parse HEAD
```

验收条件：Git clean，新提交仅包含三份治理文档。

### Step 5：生产数据与 RAG 保护

在重启前保存：

- SQLite 在线备份和 SHA-256；
- `integrity_check`、`foreign_key_check`；
- Alembic revision `0012_internal_production_finalization_v1`；
- 关键表计数；
- active collection、collection 列表和 chunks 数量；
- 当前模型 readiness；
- 当前四服务 PID/监听端口/健康结果。

不得执行 migration，不得重建 RAG，不得修改运行记录以绕过检查。

### Step 6：在同一静默窗口受控重启

```powershell
cd C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS
.\scripts\windows\stop_ai_customer_service.ps1
.\scripts\windows\start_ai_customer_service.ps1
.\scripts\windows\status_ai_customer_service.ps1
```

不得在 docs-only 提交后长期保留“新 HEAD + 旧 Runtime SHA”的混合状态。

### Step 7：重启后 Gate 验证

- 5173、5174、8000、8011 全部健康；
- 四服务 Repository Root 均为正式 `AI-CS`；
- 四服务 SHA 全部等于新的 docs-only 提交 SHA；
- 四服务 `sourceFingerprint=True`，Git 为 clean；
- `runtimeMode=standard`、`networkMode=LAN`；
- 数据库仍为 revision 0012，完整性与关键计数不变；
- RAG 仍使用 `test_knowledge_v031`，chunks 仍为 56；
- A 模型保持 ready/configured；
- B/Admin 页面 HTTP 200。

### Step 8：进入 Phase 4.1 业务验收

仅当 Step 7 全部通过，才能开始：

1. R003：C 创建/启用业务数据到 B 可用的完整业务验收；
2. R005：客服反馈 → C 问题中心 → 知识优化 → AI 改善的真实闭环验收。

---

## 5. 风险与控制

| 等级 | 风险 | 触发条件 | 控制措施 |
|---|---|---|---|
| P0 | 提交后运行身份出现 SHA 混合 | 只提交、不及时重启 | 提交与重启放在同一静默窗口；提交后立即执行身份切换验证 |
| P0 | docs-only 提交混入业务代码或 Runtime 文件 | 使用宽泛暂存命令 | 只按三个精确路径暂存；复核 cached name-status；禁止 `git add .` |
| P1 | 重启失败造成服务中断 | 环境、端口或依赖异常 | 重启前保存 PID/配置/健康证据；使用标准脚本；保留回滚锚点 |
| P1 | 启动过程意外修改数据库/RAG | 配置漂移或错误启动模式 | 确认 standard 配置；禁止 migration/RAG rebuild；前后比对 revision、hash/manifest 和计数 |
| P1 | clean Worktree 变成第二正式来源 | 采用方案 B 并长期保留 | 方案 B 仅作隔离后备，不作为正式 Runtime；优先方案 A |
| P1 | 三份文档未同步远端造成团队基线不一致 | 仅本地提交 | Runtime Gate 完成后另设受控 push 任务；push 不与生产验收混杂 |
| P2 | 本报告本身增加一个 dirty 文件 | 报告生成但未提交 | 将本报告纳入同一次 docs-only 提交，不另拆提交 |

回滚原则：

- 如果文档提交成功但服务切换失败，不修改数据库，不执行 downgrade；
- 立即用已记录的旧 SHA/Runtime 配置恢复原服务；
- 使用重启前 SQLite/RAG manifest 判断是否发生意外变化；
- 只有健康和身份一致后才重新开放验收窗口。

---

## 6. 验收标准

### 6.1 本报告任务验收标准

- [x] 已确认正式仓库 branch、HEAD、dirty 文件和 Worktree 状态；
- [x] 已确认四服务 Repository Root、SHA、source fingerprint、运行模式和健康；
- [x] 已确认数据库 revision、完整性、关键计数及 RAG/model 健康；
- [x] 已比较方案 A 与方案 B 对 Runtime、数据库和当前服务的影响；
- [x] 已给出最小恢复方案和明确执行边界；
- [x] 本轮未提交、未重启、未修改生产数据或业务代码。

本报告任务最终状态：

```text
AI_CS_PHASE_4_1_PREFLIGHT_REPORT_READY
```

### 6.2 后续 Controlled Runtime Gate 验收标准

以下项目尚待后续授权执行：

- [ ] 新提交仅包含三份 `docs/control/**` 治理文档；
- [ ] `git status --porcelain` 为空；
- [ ] 正式项目仍只有一个长期运行 Worktree；
- [ ] 四服务全部记录同一个新 SHA；
- [ ] 四服务 `sourceFingerprint=True`；
- [ ] 5173/5174/8000/8011 健康；
- [ ] Runtime 保持 `standard + LAN`；
- [ ] 数据库仍为 revision 0012，完整性和业务计数不变；
- [ ] RAG active collection 和 56 chunks 不变；
- [ ] 未修改 R006/R009 核心逻辑；
- [ ] 生成完整的提交、重启、健康和回滚证据。

全部满足后，下一 Gate 状态应为：

```text
AI_CS_PHASE_4_1_CONTROLLED_RUNTIME_BASELINE_READY
```

在此之前，不得开始 R003/R005 正式业务验收。
