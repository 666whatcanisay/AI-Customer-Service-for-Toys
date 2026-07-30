# AI-CS Source Freeze Closure Report V1

> 需求：R008 AI-CS Project Structure Simplification V1
>
> 阶段：Phase 1.5 — Source Clean & Protection Reference Closure
>
> 日期：2026-07-30
>
> 执行边界：仅治理 `docs/control/**` 与 Git 保护引用；未创建目标目录，未移动或删除文件/Worktree，未修改代码、UI、contracts、数据库、业务数据或运行服务。

## 1. 结论

Source Freeze 的两个前置阻塞可以在本阶段关闭：

1. `19cc826...`之上的8个未提交Control路径均属于R008正式治理资产，不是临时实验；它们与本报告一起形成一个仅含`docs/control/**`的独立提交。
2. 源码保护引用固定为annotated tag `ai-cs-monorepo-source-freeze-v1`；该引用指向本次闭环提交，其直接父提交为`19cc82682074dc0f11096d4191ad8d19a9f0cc0b`。
3. 当前Pilot运行与回滚仍固定在`ai-cs-pilot-baseline-v1@cbc77ed883cb99e2eff76ccb8eb3193bbddaba38`，本阶段不切换运行。

本报告提交并建立保护Tag、复核工作树clean及四服务不变后，Gate为：

```text
PASS
SOURCE_FREEZE_CLOSED
PHYSICAL_MIGRATION_ENTRY_READY
```

`PHYSICAL_MIGRATION_ENTRY_READY`只表示下一阶段具备入口，不表示已经迁移，也不授权删除旧目录、退役Worktree或切换Pilot。

## 2. Freeze状态

| 项目 | 结论 | 证据 |
| --- | --- | --- |
| 迁移内容基线 | 已冻结 | `control/r006-interface-validation-v1-1@19cc82682074dc0f11096d4191ad8d19a9f0cc0b` |
| 迁移源物理目录 | 已确认 | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-r006-interface-validation-v1` |
| 用户给出的源码锚点名称 | 作为逻辑名称保留 | `AI-CS-r006-interface-validation-v1-1`不是当前物理目录；实际目录见上项 |
| contracts | 已冻结 | `0.2.0`，本阶段未修改 |
| 业务实现树 | 已冻结 | `backend`、`frontend`、`extension`、`platform_backend`、`admin_web`、`contracts`、`scripts`、`tests`在`19cc826...`与`cbc77ed...`之间tree object一致 |
| Control覆盖层 | 正式收敛 | 8个既有路径加本报告，仅提交`docs/control/**` |
| 目标`AI-CS/` | 未创建 | 本阶段前后均不存在 |
| Pilot运行 | 原位保护 | 5173、5174、8000、8011继续从Recovery根运行；只读health均为HTTP 200 |

## 3. 未提交Control文档归属与提交决定

### 3.1 资产判定

| 路径 | 资产类型 | 判定 | 本次处理 |
| --- | --- | --- | --- |
| `docs/control/AI-CS-Monorepo-Migration-Plan-V1.md` | R008迁移治理计划 | 正式治理资产 | 保留并提交 |
| `docs/control/AI-CS-Monorepo-Source-Freeze-Report-V1.md` | Source Freeze证据 | 正式治理资产 | 保留并提交 |
| `docs/control/AI-CS-Requirement-Registry-V1.md` | 长期需求台账 | 正式治理资产 | 同步并提交 |
| `docs/control/AI-CS-Current-Requirement-Status-Summary.md` | 需求状态快照 | 正式治理资产 | 同步并提交 |
| `docs/control/01_三线状态看板.md` | Control状态看板 | 正式治理资产 | 同步并提交 |
| `docs/control/10_变更记录.md` | 审计变更记录 | 正式治理资产 | 同步并提交 |
| `docs/control/11_交接说明.md` | 跨窗口交接入口 | 正式治理资产 | 同步并提交 |
| `docs/control/machine-context.json` | 当前机器可读总控上下文 | 正式治理资产 | 同步并提交 |
| `docs/control/AI-CS-Source-Freeze-Closure-Report-V1.md` | Phase 1.5闭环证据 | 正式治理资产 | 新增并提交 |

上述文件共同描述R008从Inventory、Migration Plan、Source Freeze到Closure的连续治理事实。若不提交，未来迁移无法由单一Git引用复现，因此不采用外部临时归档方案。

### 3.2 提交边界

允许提交的路径只有上表9项，全部位于`docs/control/**`。提交必须使用逐路径选择，不得使用`git add .`。以下路径本阶段提交数量必须为零：

- `backend/**`、`frontend/**`、`extension/**`
- `platform_backend/**`、`admin_web/**`
- `contracts/**`、`scripts/**`、`tests/**`
- 数据库、`.runtime/**`、日志、向量、知识源、客户数据和构建产物

## 4. Source SHA与Runtime SHA关系

```text
ai-cs-pilot-baseline-v1
  └─ cbc77ed883cb99e2eff76ccb8eb3193bbddaba38
       │  当前Pilot运行/回滚锚点
       │
       └─ ... → 19cc82682074dc0f11096d4191ad8d19a9f0cc0b
                    │  迁移内容基线；业务实现树与cbc一致
                    │
                    └─ Source Freeze Closure文档提交
                         └─ ai-cs-monorepo-source-freeze-v1
                              未来Physical Migration唯一源码入口
```

- `cbc77ed...`是`19cc826...`的祖先。
- 两者在A/B/C、extension、contracts、scripts、tests的Git树一致，差异只属于后续Control接口与治理文档。
- 当前运行SHA不因本次文档提交而变化；源码保护SHA也不被宣称为当前运行SHA。
- 为避免文档自引用循环，本文件不内嵌其自身最终commit SHA；`git rev-parse ai-cs-monorepo-source-freeze-v1^{commit}`的结果是权威闭环SHA。

## 5. Protection Reference

### 5.1 运行锚点

| 属性 | 值 |
| --- | --- |
| 逻辑名称 | `AI-CS-pilot-baseline-recovery-v1` |
| 物理路径 | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-pilot-baseline-recovery-v1` |
| Branch | `control/pilot-baseline-recovery-v1` |
| SHA | `cbc77ed883cb99e2eff76ccb8eb3193bbddaba38` |
| Tag | `ai-cs-pilot-baseline-v1` |
| 用途 | 当前5173 B、5174 C Admin、8000 A、8011 C API的实际运行来源，也是迁移失败时的原位回滚锚点 |

禁止操作：

- 不得移动、改名、删除、force-clean或退役该目录。
- 不得从迁移源的过期运行记录停止或替换其中服务。
- 不得修改其数据库、向量、知识、日志、PID/运行记录或业务数据。
- 未完成后续同SHA启动、健康检查、功能等价、数据保护与回滚演练前，不得切换Pilot身份。

### 5.2 源码锚点

| 属性 | 值 |
| --- | --- |
| 逻辑名称 | `AI-CS-r006-interface-validation-v1-1` |
| 实际物理路径 | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-r006-interface-validation-v1` |
| Branch | `control/r006-interface-validation-v1-1` |
| 内容基线SHA | `19cc82682074dc0f11096d4191ad8d19a9f0cc0b` |
| 保护引用 | `ai-cs-monorepo-source-freeze-v1` |
| 用途 | 保存R001–R006既有代码、contracts 0.2.0、R006冻结文档和R008完整迁移治理文档，作为未来Physical Migration唯一源入口 |

禁止从逻辑名称推断不存在的物理路径。后续迁移必须先解析保护Tag并确认其直接父提交、提交路径和工作树clean，不能只依赖目录名或短SHA。

## 6. 数据库与运行数据保护规则

1. 禁止删除、重建、清空、迁移或就地修改当前数据库；结构迁移不承担数据库迁移职责。
2. 当前运行SQLite位于Recovery根的Git忽略`.runtime/data/`范围，必须原位保留；任何备份必须使用SQLite在线备份能力，不得复制正在写入的数据库文件冒充一致性备份。
3. `.runtime/**`、数据库、向量、知识源、日志、PID/运行记录、模型、依赖、构建产物和客户数据不得进入Git，也不得复制进仓库内`archive/`。
4. 源码目录迁移和运行数据迁移必须分开授权、分开执行、分开验收。未来新目录首次运行应指向明确批准的数据副本或配置，不得隐式发现旧路径。
5. 当前服务不得因“目录结构已准备”被停止或重启。正式切换必须由独立Runtime Gate记录repository root、branch/tag、SHA、clean、端口/PID、health和回滚点。
6. 任何无法分类的文件先隔离并保持原位，不得自动加入Git、archive或新运行目录。

## 7. 保护资产

- R001：C商品知识运营中心V2及其知识模板、知识状态、知识缺口。
- R002：Customer Feedback Loop的B事件、C问题中心、知识优化链路与contracts。
- R003/R006：Business Catalog Interface Freeze与Validation文档；仍禁止进入Implementation。
- R004：`ai-cs-pilot-baseline-v1`、Recovery运行根、contracts 0.2.0和既有测试证据。
- B：客服页面、AI回答、反馈能力。
- C：商品知识中心、商品维护、FAQ、安全规则、知识缺口、导入中心、AI问题分析。
- A：既有RAG、模型调用和检索能力；本阶段没有修改A。
- 运行数据：SQLite、知识、向量、日志及受管运行记录，全部保持Git外和原路径。

## 8. 未解决风险

| 风险 | 级别 | 当前处理 | 是否阻塞Physical Migration入口 |
| --- | --- | --- | --- |
| 源码保护Tag目前只在本地仓库建立，尚无远端或离线bundle副本 | P1 | 后续发布/退役前需另行授权持久化到远端或受控备份 | 否；但阻塞旧源目录退役 |
| 另有8个既存dirty Worktree、4个detached Worktree | P1 | 全部继续隔离，逐目录完成功能归属与commit/Tag复核前不得删除或force-clean | 否；但阻塞对应Worktree退役 |
| 当前Pilot运行SHA为`cbc77ed...`，未来迁移源为Closure保护Tag | P0运行边界 | 当前保持原位；未来必须完成新目录同SHA/内容等价和受控切换 | 否；但阻塞运行切换 |
| R006 IV11-B01/B02仍未关闭 | P0业务接口 | 与R008并行，结构迁移不得夹带Business Data Activation | 否；继续阻塞R006 Implementation |
| R007第二终端网络Gate未关闭 | 外部阻塞 | 由OPS/公司网络独立处理 | 否；不转化为结构或代码问题 |

## 9. Gate判定与下一阶段边界

| Gate | 判定 | 关闭证据 |
| --- | --- | --- |
| SF-B01 Control覆盖层未收敛 | `CLOSED` | 9项正式Control资产形成单一、选择性文档提交；无代码或contracts混入 |
| SF-B02 缺少源码保护引用 | `CLOSED` | annotated tag `ai-cs-monorepo-source-freeze-v1`指向Closure提交 |
| Runtime保护 | `PASS` | Recovery根clean，现有四服务来源/PID匹配且health 200；本轮未修改服务 |
| 数据保护 | `PASS` | 数据库、知识、向量、日志和运行数据均未修改、移动或加入Git |
| Physical Migration入口 | `ALLOW_WITH_GATES` | 只允许在用户另行明确授权后，从保护Tag开始Phase 2 |

允许进入下一阶段的含义仅为：可以另开受控任务创建目标`AI-CS/`并执行计划内目录迁移。下一阶段仍必须遵守：

- 先解析并记录`ai-cs-monorepo-source-freeze-v1`的commit；
- 不删除或移动Recovery运行锚点；
- 不清理既有dirty Worktree；
- 不修改业务代码、UI、接口、contracts、数据库、A/RAG/Prompt；
- 不自动切换5173、5174、8000、8011；
- 迁移失败立即停止，目标目录可丢弃，原运行锚点保持服务连续。

最终状态：`SOURCE_FREEZE_CLOSED`
