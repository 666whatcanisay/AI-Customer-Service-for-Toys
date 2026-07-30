# AI-CS Phase B Source Tree Manifest V1

> 生成日期：2026-07-30
>
> 作用：记录R008 Phase B唯一源码Tag的Git树身份；不包含工作区文件复制结果、依赖、运行数据或业务数据。

## 1. Source身份

| 项目 | 值 |
| --- | --- |
| Source Repository | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-r006-interface-validation-v1` |
| Source Ref | `ai-cs-monorepo-source-freeze-v1`（annotated tag） |
| Tag Object | `6b9ba42e93941b3377eb8b9c4f3ec185f771625f` |
| Commit | `26f8cde1e8f7373315baa1ac68d02f7823b4de82` |
| Root Tree | `9940eb270e340f6e47c325be28a57979e35c0c39` |
| Contracts | `0.2.0` |
| `contracts/version.json` Blob | `acc20d38f0f3d61aff5a280aa3beae230acfcbae` |

用户输入的`26f8cde1e8f7373315baa1ac68d02f782f771625f`不是仓库中的Commit：它把真实Commit前段与annotated tag对象后段组合在了一起。本清单按Tag实际解引用结果记录，不猜测或创建替代SHA。

## 2. 清单算法与结果

Source清单通过Git对象读取，不读取dirty Worktree内容。规范化条目格式为：

```text
<mode>\t<blob-object>\t<literal-path>\n
```

路径使用`core.quotePath=false`的UTF-8字面值，按`git ls-tree -r --full-tree`顺序排列，末尾保留一个LF。对完整规范化清单计算SHA-256。

| 指标 | 结果 |
| --- | --- |
| 跟踪文件总数 | `542` |
| 文件mode | `100644 × 542` |
| 规范化清单SHA-256 | `4476ffb7c79c602753c11d32e8b60d6517df33953b6d604284acc031f73fc7c4` |

## 3. 冻结目录清单

| 目录 | 文件数 | Git Tree |
| --- | ---: | --- |
| `backend` | 40 | `46f1f4aa0ee755393bf78ce1ee92dad9a8c7875e` |
| `frontend` | 79 | `4d799481555c34407f9f05c3ac05a3b54eb356c5` |
| `extension` | 1 | `a59d7037e4b998c9555f279c89e1a27944fc385f` |
| `platform_backend` | 97 | `236ab010ec6d93fe389c0408b5698cdebd4c6b19` |
| `admin_web` | 74 | `b16494deab348a689164acb348d4d974737cd748` |
| `contracts` | 13 | `0d5ed3f5d06cc9a6c36a8973c1f9d25c41764640` |
| `docs` | 158 | `07f162417a22616d478f3288baa9ff96e3bb8bfe` |
| `scripts` | 56 | `d28a084515aa638fcd731d75a944dc5b866ad7d9` |
| `tests` | 2 | `333267b947df8e3e6332709a6c5242f3841197d5` |

其余跟踪资产为`.agents` 9个、`.github` 5个、根文件7个及`logs/README.md` 1个。它们属于同一冻结Tree，并已纳入总数与SHA-256；`logs/README.md`只是目录边界说明，不是运行日志。

## 4. 边界

- 清单不含`.runtime`、数据库、知识源、向量、运行日志、模型、依赖或构建产物。
- 清单不把Source当前Control HEAD、其他Worktree或未提交文件作为迁移来源。
- 本文件是Control证据，不属于冻结Source Tree；它不会被补入Target或改变Source Tag。

清单状态：`SOURCE_MANIFEST_FROZEN`
