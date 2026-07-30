# AI-CS Physical Migration Preflight Checklist V1

> 需求：R008 AI-CS Project Structure Simplification V1
>
> 阶段：Phase 2A — Preflight + Target Repository Creation Preparation
>
> 日期：2026-07-30
>
> 检查性质：只读；未创建目标目录，未clone、checkout、移动、删除、安装、重启或切换。

## 1. Gate结论

本次Preflight对Source、Runtime、Target、数据库、功能保护和回滚锚点执行了只读检查。创建前条件通过，但目标仓库创建本身没有执行。

```text
PREFLIGHT_PASS
TARGET_REPOSITORY_CREATION_READY
TARGET_REPOSITORY_NOT_CREATED
```

`TARGET_REPOSITORY_CREATION_READY`只允许后续在用户明确授权下执行Phase 2A目标仓库创建；不授权Phase B代码物化、依赖安装、测试、运行切换或旧目录处理。

## 2. 强制Preflight Checklist

| ID | 必须确认项 | 只读证据 | 结果 |
| --- | --- | --- | --- |
| PF-01 | 源码来源只能是`ai-cs-monorepo-source-freeze-v1` | Tag类型为annotated `tag`；解引用到`26f8cde1e8f7373315baa1ac68d02f7823b4de82`，父提交为`19cc82682074dc0f11096d4191ad8d19a9f0cc0b` | `PASS` |
| PF-02 | 当前Control工作区不能作为代码来源 | Preflight开始时branch为`control/r006-interface-validation-v1-1@873192dded025e0dce54d0541ab0fa6869edb7ad`且clean；本报告的后续文档提交也不得成为代码来源，代码物化始终固定使用Source Tag | `PASS` |
| PF-03 | 运行来源为`ai-cs-pilot-baseline-v1@cbc77ed...` | Runtime Tag、branch和HEAD均解析到`cbc77ed883cb99e2eff76ccb8eb3193bbddaba38`，Recovery工作树clean | `PASS` |
| PF-04 | 运行继续保持Recovery目录 | 四份受管记录的repository root均为`AI-CS-pilot-baseline-recovery-v1`、记录SHA为`cbc77ed...`、source state为`CLEAN` | `PASS` |
| PF-05 | 当前四服务不受影响 | 5173/5174/8000/8011监听PID分别为33360/38224/24844/44428；B、C Admin、A、C API只读HTTP检查均为200 | `PASS` |
| PF-06 | 目标`AI-CS/`当前不存在 | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`不存在，也未出现在`git worktree list`登记中；父目录可解析 | `PASS` |
| PF-07 | 目标介质具备创建容量 | 使用`.NET DriveInfo`只读核验C盘NTFS可用约291.62 GiB；`Get-PSDrive`在本环境返回无效0值，不作为容量Gate | `PASS` |
| PF-08 | 数据库不迁移、不重建、不清空 | Recovery SQLite只读确认存在，大小733,184 bytes；`.runtime`被Git忽略；本轮没有打开业务表、复制、哈希或写入数据库 | `PASS` |
| PF-09 | 知识、向量和运行数据不进入目标 | Recovery `backend/vector_db`存在并保持原位；`.runtime`、日志、知识源、向量、模型和客户数据继续禁止复制进Git/archive | `PASS` |
| PF-10 | B/C/A功能保护入口存在 | 在Source Tag tree中核对19个B/C/A核心入口，缺失0；详见第3节 | `PASS`（静态存在） |
| PF-11 | contracts保持不变 | 从Source Tag直接读取`contracts/version.json`为`0.2.0`；本轮未修改`contracts/**` | `PASS` |
| PF-12 | 失败可以回到Recovery | Recovery物理根、运行Tag、branch、clean状态、受管记录、监听PID和四项health均可用 | `PASS` |
| PF-13 | 非来源Worktree继续隔离 | Git登记69个Worktree，其中8个dirty、4个detached；它们未参与Preflight且不得作为复制源 | `PASS` |
| PF-14 | 实际创建动作未发生 | 目标目录不存在；没有执行clone、checkout、文件复制、依赖安装或服务操作 | `PASS` |

## 3. 功能保护静态清单

本节只证明冻结Tag中正式入口存在，不替代Phase D自动化测试或Phase E真实运行验收。

### 3.1 B — 客服工作台

| 能力 | Source Tag入口 | Preflight |
| --- | --- | --- |
| 客服聊天与选品 | `frontend/src/views/AiChat.vue` | 存在 |
| AI回答 | `frontend/src/api/ragClient.ts` | 存在 |
| 采用行为记录 | `frontend/src/api/aiInteractionEventClient.ts` | 存在 |
| AI问题反馈 | `frontend/src/api/aiResponseFeedbackClient.ts` | 存在 |

保护要求：Phase B必须保持`frontend/**`与`extension/**`原目录；不得修改UI、回答流程、反馈回执或人工确认边界。

### 3.2 C — 运营中心与Platform API

| 能力 | Source Tag入口 | Preflight |
| --- | --- | --- |
| 商品知识中心 | `platform_backend/app/product_knowledge/service.py`、`admin_web/src/views/KnowledgeCenterView.vue` | 存在 |
| 商品维护 | `platform_backend/app/operation_management/service.py`、`StoreManagementView.vue`、`ProductDetailView.vue` | 存在 |
| FAQ与安全规则 | `platform_backend/app/test_catalog/service.py`、`knowledge_materials/service.py` | 存在 |
| 知识缺口 | `KnowledgeGapCenterView.vue` | 存在 |
| 导入中心 | `platform_backend/app/ingestion/service.py`、`ImportCenterView.vue` | 存在 |
| AI问题分析 | `customer_feedback_loop/service.py`、`AiIssueCenterView.vue` | 存在 |

保护要求：Phase B必须保持`platform_backend/**`和`admin_web/**`原目录；不得修改UI、数据库、Alembic、接口或R006业务状态。

### 3.3 A — AI能力层

| 能力 | Source Tag入口 | Preflight |
| --- | --- | --- |
| RAG | `backend/app/service/rag_service.py` | 存在 |
| 检索 | `backend/app/service/vector_store.py`、`document_loader.py` | 存在 |
| 模型调用 | 由既有`rag_service.py`及配置/API入口承载 | 存在 |

保护要求：Phase B必须保持`backend/**`原目录；不得修改模型、Prompt、RAG、检索范围或向量数据。

## 4. Runtime保护记录

| 服务 | 端口 | managed PID | listener PID | 运行根 | SHA | 只读health |
| --- | ---: | ---: | ---: | --- | --- | --- |
| B客服工作台 | 5173 | 33360 | 33360 | `AI-CS-pilot-baseline-recovery-v1` | `cbc77ed...` | `/` 200 |
| C Admin | 5174 | 30732 | 38224 | 同上 | `cbc77ed...` | `/` 200 |
| A能力层 | 8000 | 20384 | 24844 | 同上 | `cbc77ed...` | `/api/health` 200 |
| C API | 8011 | 19020 | 44428 | 同上 | `cbc77ed...` | `/health` 200 |

本轮没有停止、重启、修改或替换任何服务。Phase 2A实际创建也不得访问标准端口、读取过期运行记录执行停止，或改变Recovery根。

## 5. 数据保护确认

1. 代码创建阶段不迁移业务数据。
2. 不复制Recovery `.runtime`、SQLite、日志、PID记录、知识、向量、模型、依赖或构建产物。
3. 不执行Alembic、数据库初始化、知识导入、向量同步或数据清理。
4. 目标仓库创建阶段只创建独立Git元数据；工作树保持未签出，不创建目标`.runtime`。
5. 数据库路径、大小只作为存在性证据；不读取客户内容、知识正文或业务记录。
6. 如果未来目标运行仍引用Recovery数据，Recovery目录继续是运行依赖，禁止归档或删除。

## 6. 回滚确认

Phase 2A目标仓库创建发生在当前Pilot之外，不需要停止旧服务。若创建失败：

1. 立即停止后续Git操作，不进入Phase B。
2. 保留失败命令、退出码和目标目录状态的脱敏证据。
3. Recovery根与四服务继续保持原样，不执行运行回滚动作。
4. 只有在重新核验目标绝对路径且获得删除授权后，才能移除未使用的失败目标目录。
5. 再次执行时仍从`ai-cs-monorepo-source-freeze-v1`开始，不从失败目录或dirty Worktree补文件。

若未来Phase E切换失败，运行回滚固定到`AI-CS-pilot-baseline-recovery-v1@cbc77ed...`，按可信记录恢复C API → A → B → C Admin，并复核SHA、PID、health、代理、功能和数据库证据。

## 7. 风险与停止条件

| 风险 | 处理 | 是否阻塞本次Ready |
| --- | --- | --- |
| Source Tag当前仅本地持久化 | 目标独立clone将形成第二份对象；旧源退役前仍需远端或受控bundle | 否，阻塞旧源退役 |
| 8个dirty、4个detached Worktree | 继续隔离，不复制、不清理、不删除 | 否，阻塞对应目录退役 |
| `Get-PSDrive`错误显示0可用空间 | 创建时继续使用`.NET DriveInfo`交叉验证；低于批准阈值立即停止 | 否，实际容量充足 |
| 目标同名路径以后被其他进程创建 | Phase 2A执行前重新检查；存在即停止，禁止合并/覆盖 | 否，当前不存在 |
| Recovery根仍承载运行数据 | Phase 2A不触碰；数据路径独立前禁止归档Recovery | 否，属于后续Gate |

强制停止条件：Tag/SHA不匹配、Source或Runtime不clean、Target已存在/已登记、可用空间不足、Recovery记录与listener不匹配、contracts不为0.2.0、任何功能入口缺失，或出现要求复制/修改数据库的步骤。

## 8. Preflight验收

| 验收项 | 结论 |
| --- | --- |
| Source身份 | `PASS` |
| Runtime身份与连续性 | `PASS` |
| Target路径空闲 | `PASS` |
| 数据库与运行数据边界 | `PASS` |
| B/C/A静态保护入口 | `PASS` |
| 回滚可达性 | `PASS` |
| 实际创建 | `NOT_EXECUTED` |

下一入口：用户另行明确授权的`R008 Phase 2A — Target Repository Creation Execution`。该任务只能创建独立的no-checkout目标Git仓库并验证独立性，不得进入Phase B。

最终状态：`TARGET_REPOSITORY_CREATION_READY`
