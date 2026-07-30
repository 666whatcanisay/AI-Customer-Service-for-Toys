# AI-CS Phase 2A Target Repository Creation Execution Report V1

> 需求：R008 AI-CS Project Structure Simplification V1
>
> 阶段：Phase 2A — Target Repository Creation Execution
>
> 日期：2026-07-30
>
> 执行结果：`PASS / TARGET_REPOSITORY_CREATED`
>
> 下一阶段：`PHASE_B_NOT_AUTHORIZED`

## 1. 创建结果

目标独立Git仓库已成功创建：

| 属性 | 结果 |
| --- | --- |
| 目标路径 | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS` |
| 创建方式 | `git clone --no-hardlinks --no-checkout` |
| 文件系统复制 | 未使用`Copy-Item`、`robocopy`、压缩包或资源管理器复制 |
| Worktree方式 | 未使用`git worktree add` |
| 共享对象 | 未使用`--shared`或`--reference`；无alternates |
| 目标根内容 | 仅`.git/`目录 |
| 代码checkout | 未执行；核心代码目录数量为0 |
| 依赖/.runtime | 未安装、未创建 |
| Source Tag | `ai-cs-monorepo-source-freeze-v1@26f8cde1e8f7373315baa1ac68d02f7823b4de82` |
| Runtime Tag | `ai-cs-pilot-baseline-v1@cbc77ed883cb99e2eff76ccb8eb3193bbddaba38` |

实际执行命令：

```powershell
git clone --no-hardlinks --no-checkout `
  "C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-r006-interface-validation-v1" `
  "C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS"
```

命令退出码为0。Clone后立即停止写入目标仓库，未创建迁移分支、未改变目标HEAD、未checkout文件。

## 2. 执行前Preflight复核

实际创建前重新核验：

| 项目 | 复核结果 |
| --- | --- |
| Source Tag | annotated tag，解引用`26f8cde...`，父提交`19cc826...` |
| Source Control工作树 | `control/r006-interface-validation-v1-1@cfa2a0fa91788accb29575716d269371750e5c8a`，clean |
| Runtime | `control/pilot-baseline-recovery-v1@cbc77ed...`，clean |
| contracts | Source Tag内`0.2.0` |
| Target | 不存在 |
| C盘可用容量 | 约291.61 GiB |
| Recovery SQLite | 存在，733,184 bytes；只读元数据核验 |
| 监听PID | 5173=`33360`、5174=`38224`、8000=`24844`、8011=`44428` |
| 四项health | B、C Admin、A、C API均HTTP 200 |

创建前条件全部通过，没有使用旧Control HEAD作为代码checkout来源。Source Tag继续是未来Phase B唯一代码物化入口。

## 3. Git独立性验证

### 3.1 GI结果

| GI | 验证内容 | 实际证据 | 结果 |
| --- | --- | --- | --- |
| GI-01 | `.git`独立 | `AI-CS/.git`是目录，不是指向旧common dir的gitfile | `PASS` |
| GI-02 | git-dir正确 | absolute git-dir为`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS\.git` | `PASS` |
| GI-03 | common-dir不指向旧仓库 | git-common-dir与目标`.git`相同，不位于旧`666.../.git` | `PASS` |
| GI-04 | Worktree独立 | 目标仓库只登记自身1个Worktree；源仓库仍登记原69个且不含目标 | `PASS` |
| GI-05 | Source Tag可解析 | 目标内Tag类型为annotated `tag`，解引用`26f8cde...` | `PASS` |
| GI-06 | Runtime Tag可解析 | 目标内`ai-cs-pilot-baseline-v1`解引用`cbc77ed...` | `PASS` |
| GI-07 | 没有checkout代码 | 目标根只有`.git`；`backend/frontend/...`及`.runtime`均不存在 | `PASS` |
| GI-08 | 无alternates依赖 | `.git/objects/info/alternates`不存在；clone使用`--no-hardlinks`且无共享对象选项 | `PASS` |
| GI-09 | Source未变化 | GI验证时Source Tag仍为`26f8cde...`、Control工作树clean、源Worktree登记仍为69 | `PASS` |
| GI-10 | Runtime未变化 | Runtime仍为clean `cbc77ed...`；四份受管记录、listener PID和health保持一致 | `PASS` |

GI-01至GI-10：`10 PASS / 0 FAIL`。

### 3.2 Target Git当前身份

| 属性 | 当前值 | 解释 |
| --- | --- | --- |
| git-dir/common-dir | 目标自身`AI-CS/.git` | 满足独立性 |
| Worktree登记 | 仅`AI-CS`自身 | 不是linked Worktree |
| 当前HEAD | `cfa2a0fa91788accb29575716d269371750e5c8a` |
| 当前HEAD ref | `refs/heads/control/r006-interface-validation-v1-1` |
| 工作树 | 未checkout、只有`.git` |
| origin | 本地Source路径 |

Clone复制了源仓库refs，因此未签出Target HEAD仍指向clone时的Control分支。该状态不代表代码已经物化，也不改变唯一代码来源。Phase B禁止直接checkout当前HEAD；必须在另行授权后显式从`ai-cs-monorepo-source-freeze-v1@26f8cde...`创建迁移分支并物化冻结tree。

Origin保存本地Source路径只作为未来fetch/push配置，不构成Git对象或common-dir依赖。旧源退役前仍需在单独治理任务中设置长期remote并持久化保护Tag；本阶段不修改remote。

## 4. Source与Runtime保护复核

### 4.1 Source

- `ai-cs-monorepo-source-freeze-v1`仍解引用到`26f8cde...`。
- 创建与GI验证过程中Source Control HEAD保持`cfa2a0f...`且clean。
- 源仓库Worktree登记仍为69，目标没有被加入旧仓库Worktree列表。
- 8个dirty、4个detached Worktree继续原位隔离，没有被复制、移动、清理或删除。
- 本报告及状态同步会在GI完成后形成独立`docs/control/**`治理提交；它只记录证据，不改变Source Tag或任何业务代码。

### 4.2 Runtime

| 服务 | managed PID | listener PID | 记录root/SHA | HTTP |
| --- | ---: | ---: | --- | --- |
| B 5173 | 33360 | 33360 | Recovery / `cbc77ed...` | 200 |
| C Admin 5174 | 30732 | 38224 | Recovery / `cbc77ed...` | 200 |
| A 8000 | 20384 | 24844 | Recovery / `cbc77ed...` | 200 |
| C API 8011 | 19020 | 44428 | Recovery / `cbc77ed...` | 200 |

Runtime工作树仍clean。Recovery数据库继续存在且大小保持733,184 bytes；本轮未读取业务表、复制数据库、修改知识/向量、停止/重启服务或改变运行记录。

## 5. 禁止阶段执行确认

| 阶段 | 状态 | 本轮证据 |
| --- | --- | --- |
| Phase B代码物化 | `NOT_EXECUTED` | 目标根无核心代码目录，没有checkout |
| Phase C依赖安装 | `NOT_EXECUTED` | 无`.venv`、`node_modules`、lockfile操作 |
| Phase D测试 | `NOT_EXECUTED` | 未执行应用测试；仅做GI和只读health |
| Phase E运行切换 | `NOT_EXECUTED` | 四服务继续来自Recovery，同PID |
| Phase F旧目录处理 | `NOT_EXECUTED` | 69个源Worktree登记保持，未移动/删除 |

contracts、UI、数据库、A模型、Prompt、RAG和业务逻辑均未修改。

## 6. 失败回滚情况

Clone一次成功，未出现partial target、Git独立性失败或运行异常，因此没有执行回滚、删除或重试。

若GI失败，预定处置是：停止所有目标写操作，保持目标部分目录原位等待授权，不触碰Source或Recovery；本次未触发该路径。

Recovery锚点始终保持可用，因此创建动作对当前Pilot没有运行回滚需求。

## 7. Gate判定

| Gate | 判定 |
| --- | --- |
| Preflight复核 | `PASS` |
| 独立no-checkout clone | `PASS` |
| GI-01至GI-10 | `PASS` |
| Source保护 | `PASS` |
| Runtime保护 | `PASS` |
| 数据库/数据保护 | `PASS` |
| Phase B–F未执行 | `PASS` |

Phase 2A结论：`TARGET_REPOSITORY_CREATED`。

## 8. 下一阶段入口

下一入口是另行明确授权的`R008 Phase B — Source Tag Code Materialization Preparation/Execution`。当前只具备入口条件，不表示Phase B已经授权。

Phase B必须：

1. 再次确认Target只含`.git`、GI-01至GI-10仍通过。
2. 禁止直接checkout当前Target HEAD。
3. 显式以`ai-cs-monorepo-source-freeze-v1@26f8cde...`为起点创建迁移分支。
4. 只物化冻结tree，保留核心目录原名。
5. 不安装依赖、不运行测试、不创建`.runtime`、不修改代码/UI/contracts/数据库、不触碰Recovery运行。

Phase B获得单独授权前，Target必须维持no-checkout状态。

最终状态：`TARGET_REPOSITORY_CREATED`
