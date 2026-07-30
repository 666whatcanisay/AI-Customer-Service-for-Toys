# AI-CS Phase 2A Target Repository Creation Report V1

> 需求：R008 AI-CS Project Structure Simplification V1
>
> 阶段：Phase 2A — Target Repository Creation Preparation
>
> 报告状态：`PREPARED / CREATION_NOT_EXECUTED`
>
> 日期：2026-07-30

> 后续结果：Phase 2A实际创建已完成，当前事实以[AI-CS Phase 2A Target Repository Creation Execution Report V1](AI-CS-Phase-2A-Target-Repository-Creation-Execution-Report-V1.md)为准。本文件保留为创建前计划与验收标准快照。

## 1. 当前结论

目标仓库创建的Source、Runtime、路径、容量、数据保护、功能入口和回滚条件已经通过只读Preflight。由于本阶段明确禁止实际创建目录，`AI-CS/`仍不存在，Git独立性验证尚未实际执行。

```text
PRECONDITIONS_PASS
TARGET_REPOSITORY_CREATION_READY
TARGET_REPOSITORY_CREATED = false
```

详细检查证据见[AI-CS Physical Migration Preflight Checklist V1](AI-CS-Physical-Migration-Preflight-Checklist-V1.md)。

## 2. 创建条件

| 条件 | 冻结值/要求 | 当前结果 |
| --- | --- | --- |
| 唯一Source | `ai-cs-monorepo-source-freeze-v1@26f8cde1e8f7373315baa1ac68d02f7823b4de82` | `PASS` |
| Source Tag类型 | annotated tag；父提交`19cc826...` | `PASS` |
| 运行/回滚 | `ai-cs-pilot-baseline-v1@cbc77ed883cb99e2eff76ccb8eb3193bbddaba38` | `PASS` |
| 运行根 | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-pilot-baseline-recovery-v1`，clean且继续运行 | `PASS` |
| 目标路径 | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS` | 不存在、未登记 |
| 目标父目录 | `C:\Users\EDY\Documents\Codex\2026-07-21` | 可解析 |
| 磁盘容量 | C盘NTFS可用约291.62 GiB | `PASS` |
| contracts | Source Tag内`0.2.0` | `PASS` |
| 功能保护 | 19个B/C/A核心入口在Tag tree内存在 | `PASS`（静态） |
| 数据保护 | 不迁移、不复制、不重建、不清空 | `PASS` |
| 非来源Worktree | 8个dirty、4个detached继续隔离 | `PASS` |
| 当前服务 | 四服务仍来自Recovery；监听与受管记录匹配、HTTP 200 | `PASS` |

创建前最后一刻必须重复核对Source/Runtime Tag、两个clean状态、目标不存在、父目录、容量和四个listener。任何变化都使本报告失效，必须重新执行Preflight。

## 3. 创建方式

### 3.1 执行边界

Phase 2A实际执行只允许创建一个独立、未签出工作树的Git仓库：

```text
Source Git object database
  ↓ clone --no-hardlinks --no-checkout
AI-CS/.git

工作树：空
代码文件：未物化
依赖：未安装
.runtime：未创建
服务：未启动
```

禁止使用资源管理器、`Copy-Item`、`robocopy`、压缩包、`git worktree add`或目录改名创建目标。`git worktree add`会继续依赖旧仓库common dir，不满足“未来唯一长期主目录”的Git独立性要求。

### 3.2 计划命令模板

以下仅为获批后的执行模板，本轮没有运行：

```powershell
git clone --no-hardlinks --no-checkout `
  "C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-r006-interface-validation-v1" `
  "C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS"
```

执行工具必须把clone退出码、目标路径和Tag解析写入脱敏报告。禁止加入`--shared`、`--reference`或其他对象共享方式；本计划固定使用`--no-hardlinks`，不让目标对象依赖源文件硬链接。

Clone完成后仍不得checkout。Phase 2A只验证目标独立Git元数据和Source Tag可达性；代码物化属于Phase B。

### 3.3 创建失败处理

- clone非零退出：立即停止，不重试覆盖同名目录。
- 产生部分目标：标记`PARTIAL_TARGET`，先只读记录`.git`类型、文件数量和错误；没有删除授权时保持原位。
- Target创建期间Source/Runtime变化：停止并重新Preflight。
- 发现目标引用源common dir或对象共享：判定`GIT_INDEPENDENCE_FAIL`，不得进入Phase B。
- 所有失败均保持Recovery运行，不修改数据库、不清理Worktree。

## 4. Git独立性验证

### 4.1 当前状态

目标目录尚未创建，因此以下验证状态均为`PENDING_EXECUTION`，不能在本报告中伪造为通过。

### 4.2 创建后强制验证矩阵

| ID | 验证 | 通过标准 |
| --- | --- | --- |
| GI-01 | 目标`.git`类型 | `AI-CS/.git`是目标自身目录，不是指向旧仓库的gitfile |
| GI-02 | `rev-parse --git-dir` | 解析到`AI-CS/.git`内部 |
| GI-03 | `rev-parse --git-common-dir` | 与目标自身`.git`一致，不指向`666.../.git`或任何旧Worktree |
| GI-04 | Worktree登记 | 目标仓库`git worktree list`只登记自身；旧仓库不得把`AI-CS/`登记为linked Worktree |
| GI-05 | Source Tag可达 | 目标内Tag类型仍为annotated `tag`，解引用commit严格为`26f8cde...` |
| GI-06 | Runtime Tag可达 | `ai-cs-pilot-baseline-v1`仍解析到`cbc77ed...`，仅作回滚引用 |
| GI-07 | 工作树未签出 | 核心代码目录尚不存在；Phase 2A没有物化代码 |
| GI-08 | 无对象共享依赖 | clone使用`--no-hardlinks`且未配置alternates/shared object store |
| GI-09 | Source不变 | Source Tag、源工作树和69个既有Worktree未移动、删除或修改 |
| GI-10 | Runtime不变 | Recovery branch/SHA/clean、记录、listener和health保持Preflight证据 |

建议只读验证命令：

```powershell
git -C "<target>" rev-parse --git-dir
git -C "<target>" rev-parse --git-common-dir
git -C "<target>" cat-file -t ai-cs-monorepo-source-freeze-v1
git -C "<target>" rev-parse "ai-cs-monorepo-source-freeze-v1^{commit}"
git -C "<target>" rev-parse "ai-cs-pilot-baseline-v1^{commit}"
git -C "<target>" worktree list --porcelain
git -C "<target>" config --get-all objects.infoAlternates
```

还必须检查`.git/objects/info/alternates`不存在或为空。任何Git common dir、alternates或Worktree登记指向旧目录，Gate均为`FAIL`。

## 5. Phase 2A实际验收Gate

实际创建任务只有同时满足以下条件才能输出`TARGET_REPOSITORY_CREATED`：

- [ ] Preflight在执行前重新通过。
- [ ] clone命令仅使用`--no-hardlinks --no-checkout`和批准的精确路径。
- [ ] Target创建成功且是独立Git仓库。
- [ ] GI-01至GI-10全部通过。
- [ ] Source/Runtime Tag均可达且SHA匹配。
- [ ] 工作树仍未签出，核心代码目录尚未物化。
- [ ] 没有依赖、`.runtime`、数据库、日志、知识、向量或构建产物。
- [ ] Source、Recovery运行根、旧Worktree和四服务均未改变。
- [ ] 目标路径之外没有新增或删除文件。

本轮实际结果：

| Gate | 结果 |
| --- | --- |
| Preflight | `PASS` |
| Target创建 | `NOT_EXECUTED` |
| Git独立性 | `PENDING_EXECUTION` |
| Phase B入口 | `CLOSED` |

## 6. 后续Phase B入口

Phase B是“从Source Tag物化代码”，不是Phase 2A的自动延续。只有实际创建报告补齐以下证据后，Control才能另行评审Phase B：

1. `TARGET_REPOSITORY_CREATED` Gate通过。
2. Target独立Git验证GI-01至GI-10全部通过。
3. Target内`ai-cs-monorepo-source-freeze-v1`解析到`26f8cde...`。
4. Target工作树仍未checkout，没有代码、依赖或运行数据。
5. Source和Runtime继续clean，四服务继续从Recovery根运行。
6. 新的Phase B任务卡明确只从Source Tag创建迁移分支并物化冻结tree，核心目录不改名。

Phase B仍禁止UI、业务代码、contracts、数据库、依赖升级、运行切换和旧目录删除。Phase B未获明确授权前，目标仓库即使创建成功也必须保持未签出状态。

## 7. 本轮未执行事项

本轮没有创建`AI-CS/`，没有执行clone或checkout，没有移动/删除旧目录或Worktree，没有安装依赖，没有修改代码、UI、contracts、数据库、知识、向量或运行服务，也没有创建迁移branch/Tag、push或切换Pilot。

当前Gate：`PASS / TARGET_REPOSITORY_CREATION_READY / CREATION_NOT_EXECUTED`。

最终状态：`TARGET_REPOSITORY_CREATION_READY`
