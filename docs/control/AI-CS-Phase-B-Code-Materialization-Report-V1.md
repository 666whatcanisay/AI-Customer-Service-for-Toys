# AI-CS Phase B Code Materialization Report V1

> 需求：R008 AI-CS Project Structure Simplification V1
>
> 阶段：Phase B — Source Tag Code Materialization
>
> 执行日期：2026-07-30
>
> 最终Gate：`PASS / SOURCE_TREE_MATERIALIZED / PHASE_C_NOT_AUTHORIZED`

## 1. 执行结论

冻结源码已从唯一Source Tag物化到独立目标仓库：

```text
ai-cs-monorepo-source-freeze-v1
  tag object 6b9ba42e93941b3377eb8b9c4f3ec185f771625f
  commit     26f8cde1e8f7373315baa1ac68d02f7823b4de82
  tree       9940eb270e340f6e47c325be28a57979e35c0c39
        ↓ Git checkout，未使用文件系统复制
AI-CS/control/r008-physical-migration-v1
  HEAD       26f8cde1e8f7373315baa1ac68d02f7823b4de82
  tree       9940eb270e340f6e47c325be28a57979e35c0c39
  worktree   clean
```

Source与Target均为542个跟踪文件，规范化清单SHA-256一致，条目差异为0；九个核心目录、19个功能保护入口和contracts 0.2.0均存在。没有修改业务代码、UI、contracts或数据库，没有安装依赖、创建runtime数据、启动/切换服务或进入R006。

最终状态：`SOURCE_TREE_MATERIALIZED`。

## 2. Source Tag解析

| 项目 | 实际结果 |
| --- | --- |
| Ref | `ai-cs-monorepo-source-freeze-v1` |
| Ref类型 | annotated tag |
| Tag Object | `6b9ba42e93941b3377eb8b9c4f3ec185f771625f` |
| Commit | `26f8cde1e8f7373315baa1ac68d02f7823b4de82` |
| Root Tree | `9940eb270e340f6e47c325be28a57979e35c0c39` |

任务输入中的`26f8cde1e8f7373315baa1ac68d02f782f771625f`不是可解析Commit。其前段来自实际Commit，后段来自Tag Object。任务同时规定“以实际Tag解析结果为准”，因此本轮只使用上表中的Git实际对象，不创建别名或替代提交。

## 3. Checkout结果

### 3.1 前置确认

- Target根在执行前只有独立`.git`；没有工作区文件、外部未跟踪文件或`.runtime`。
- no-checkout clone的空Index将HEAD内容显示为删除，这是尚未物化状态，不是dirty Worktree来源。
- 目标迁移分支`control/r008-physical-migration-v1`不存在。
- Source Worktree为`control/r006-interface-validation-v1-1@933f3667acf2621842420a33edfa1368abdf067e`且clean；它仅用于Tag/object校验，不是工作区复制来源。
- Runtime为`control/pilot-baseline-recovery-v1@cbc77ed883cb99e2eff76ccb8eb3193bbddaba38`且clean。

### 3.2 执行动作

在精确目标仓库执行等价动作：

```text
git switch --discard-changes -c control/r008-physical-migration-v1 ai-cs-monorepo-source-freeze-v1
```

`--discard-changes`只用于把已确认“仅`.git`”的no-checkout空工作树物化为冻结Tag内容；目标内不存在需要保留的用户文件。没有在Source或Runtime执行checkout、reset、clean、复制、移动或删除。

### 3.3 结果

| 检查 | 结果 |
| --- | --- |
| Target Branch | `control/r008-physical-migration-v1` |
| Target HEAD | `26f8cde1e8f7373315baa1ac68d02f7823b4de82` |
| Target HEAD Tree | `9940eb270e340f6e47c325be28a57979e35c0c39` |
| Target Index Tree | `9940eb270e340f6e47c325be28a57979e35c0c39` |
| Target Status | clean |
| 创建失败/回滚 | 未发生；物化一次成功 |

## 4. Tree一致性

完整清单：

- [Source Tree Manifest V1](manifests/AI-CS-Phase-B-Source-Tree-Manifest-V1.md)
- [Target Tree Manifest V1](manifests/AI-CS-Phase-B-Target-Tree-Manifest-V1.md)

| 指标 | Source | Target | 结论 |
| --- | ---: | ---: | --- |
| 跟踪文件 | 542 | 542 | PASS |
| 物理工作树文件（排除`.git`） | 不适用 | 542 | PASS |
| 规范化清单SHA-256 | `4476ffb7...fc7c4` | `4476ffb7...fc7c4` | PASS |
| 条目差异 | — | 0 | PASS |
| Root/HEAD/Index Tree | `9940eb2...` | `9940eb2...` | PASS |
| `contracts/version.json` Blob | `acc20d3...` | `acc20d3...` | PASS |

目录文件数：

| 目录 | Source | Target | Tree |
| --- | ---: | ---: | --- |
| `backend` | 40 | 40 | PASS |
| `frontend` | 79 | 79 | PASS |
| `extension` | 1 | 1 | PASS |
| `platform_backend` | 97 | 97 | PASS |
| `admin_web` | 74 | 74 | PASS |
| `contracts` | 13 | 13 | PASS |
| `docs` | 158 | 158 | PASS |
| `scripts` | 56 | 56 | PASS |
| `tests` | 2 | 2 | PASS |

所有542个文件mode均为`100644`；没有因Windows checkout引入Git mode差异。

## 5. 功能入口检查

本检查只证明冻结入口已物化且受Git跟踪，不替代Phase D自动化测试或Phase E运行验收。

### 5.1 B客服工作台

| 能力 | 冻结入口 | 结果 |
| --- | --- | --- |
| 客服聊天 | `frontend/src/views/AiChat.vue` | 存在、tracked |
| AI回答 | `frontend/src/api/ragClient.ts` | 存在、tracked |
| 采用/反馈 | `aiInteractionEventClient.ts`、`aiResponseFeedbackClient.ts` | 均存在、tracked |

### 5.2 C运营中心与Platform API

| 能力 | 冻结入口 | 结果 |
| --- | --- | --- |
| 商品知识中心 | `product_knowledge/service.py`、`KnowledgeCenterView.vue` | 均存在、tracked |
| 商品维护 | `operation_management/service.py`、`StoreManagementView.vue`、`ProductDetailView.vue` | 均存在、tracked |
| FAQ/安全规则 | `test_catalog/service.py`、`knowledge_materials/service.py` | 均存在、tracked |
| 知识缺口 | `KnowledgeGapCenterView.vue` | 存在、tracked |
| 导入中心 | `ingestion/service.py`、`ImportCenterView.vue` | 均存在、tracked |
| AI问题分析/反馈闭环 | `customer_feedback_loop/service.py`、`AiIssueCenterView.vue` | 均存在、tracked |

### 5.3 A AI能力层

| 能力 | 冻结入口 | 结果 |
| --- | --- | --- |
| RAG | `backend/app/service/rag_service.py` | 存在、tracked |
| 检索 | `backend/app/service/vector_store.py` | 存在、tracked |
| 资料加载 | `backend/app/service/document_loader.py` | 存在、tracked |

19个逐文件入口检查结果为`19/19 PASS`。

## 6. Contracts与非Git资产检查

- `contracts/version.json`实际字段`contract_version`为`0.2.0`。
- Source/Target的version Blob一致；本轮没有编辑schema、CHANGELOG或兼容说明。
- Target不存在`.runtime`、`.env`、数据库、运行日志、模型、依赖目录、Python缓存或构建目录。
- `.env.example`、tracked XLSX/CSV模板与`logs/README.md`属于冻结Git Tree；它们不是运行配置、业务数据库或运行日志。
- 没有从dirty/detached Worktree补文件，也没有把未跟踪资产解释为“缺失能力”。

## 7. Pilot运行保护结果

| 项目 | 物化后状态 |
| --- | --- |
| Runtime根 | `AI-CS-pilot-baseline-recovery-v1`，未变 |
| Runtime Branch/SHA | `control/pilot-baseline-recovery-v1@cbc77ed883cb99e2eff76ccb8eb3193bbddaba38` |
| Runtime Git | clean；`ai-cs-pilot-baseline-v1`仍解析到同一SHA |
| 5173 B | HTTP 200；listener PID 33360 |
| 5174 C Admin | HTTP 200；listener PID 38224 |
| 8000 A | `/api/health` HTTP 200；listener PID 24844 |
| 8011 C API | `/health` HTTP 200；listener PID 44428 |
| 受保护SQLite | 原位存在，733,184 bytes；未读取内容、未复制、未修改 |

Target没有启动服务，也没有占用、停止或替换标准端口。Target代码身份与当前Runtime身份保持明确分离。

## 8. 未执行事项

以下事项不在本轮授权内，全部未执行：

- Phase C依赖安装；
- Phase D测试、build、Alembic往返或数据库连接；
- Phase E隔离运行、标准端口切换、服务停止/重启；
- Phase F旧目录归档、移动、删除、Worktree退役；
- `.runtime`、数据库、知识、向量或运行记录创建/迁移；
- `archive/`结构变更；
- 业务代码、UI、contracts、数据库、RAG、模型、Prompt修改；
- R006 Business Data Activation Implementation。

因此本报告只证明“冻结Source Tree已精确物化”，不声明依赖可复现、测试通过、Target可运行、Pilot已切换或R008已关闭。

## 9. Phase C入口条件

Phase C当前为`NOT_AUTHORIZED`。只有在用户另行明确授权且以下条件复核通过后，才允许进入：

1. Target仍为`control/r008-physical-migration-v1@26f8cde...`且clean。
2. HEAD/Index Tree仍为`9940eb270e340f6e47c325be28a57979e35c0c39`。
3. Source/Target两个manifest仍为542个文件、SHA-256相同、差异为0。
4. contracts仍为`0.2.0`且lockfile/requirements未修改。
5. Target仍无`.runtime`、数据库、依赖、缓存或构建产物。
6. Runtime继续从Recovery `cbc77ed...`运行且数据库/向量原位保护。
7. Phase C只安装冻结依赖，不升级工具链、不修改lockfile、不启动服务、不连接Pilot数据库。

如果任何条件失败，Phase C不得开始；不得通过修改代码或从旧Worktree复制来修复差异。

最终状态：`SOURCE_TREE_MATERIALIZED`
