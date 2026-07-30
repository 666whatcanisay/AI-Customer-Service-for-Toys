# AI-CS Phase B Target Tree Manifest V1

> 生成日期：2026-07-30
>
> 作用：记录R008 Phase B完成后的Target工作树身份，并与Source Manifest建立零差异证据。

## 1. Target身份

| 项目 | 值 |
| --- | --- |
| Target Repository | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS` |
| Branch | `control/r008-physical-migration-v1` |
| HEAD | `26f8cde1e8f7373315baa1ac68d02f7823b4de82` |
| HEAD Tree | `9940eb270e340f6e47c325be28a57979e35c0c39` |
| Index Tree | `9940eb270e340f6e47c325be28a57979e35c0c39` |
| Worktree | `clean` |
| Contracts | `0.2.0` |
| `contracts/version.json` Blob | `acc20d38f0f3d61aff5a280aa3beae230acfcbae` |

迁移分支由`ai-cs-monorepo-source-freeze-v1`显式创建。没有直接checkout clone时的Control HEAD，也没有从任何旧目录或dirty Worktree复制文件。

## 2. 清单算法与结果

Target清单使用与Source一致的UTF-8字面路径规范，条目来自Target Git index：

```text
<mode>\t<blob-object>\t<literal-path>\n
```

| 指标 | 结果 |
| --- | --- |
| Git index文件总数 | `542` |
| 物理工作树文件总数（排除`.git`） | `542` |
| 文件mode | `100644 × 542` |
| 规范化清单SHA-256 | `4476ffb7c79c602753c11d32e8b60d6517df33953b6d604284acc031f73fc7c4` |
| Source/Target条目差异 | `0` |

## 3. 目标目录结果

| 目录 | Source文件数 | Target文件数 | Tree一致 |
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

九个核心目录保持原名。完整Root Tree、每个核心目录Tree、文件数量、mode、blob与路径均和Source Tag一致。

## 4. 非物化资产检查

以下Target资产数量均为0：

- `.runtime`目录；
- `.env`文件（`.env.example`为冻结示例文件，不属于运行配置）；
- `node_modules`、`.venv`、`venv`、`__pycache__`、`.pytest_cache`；
- `dist`、`build`；
- `*.db`、`*.sqlite`、`*.sqlite3`；
- `*.log`；
- 常见模型文件`*.bin`、`*.safetensors`、`*.gguf`、`*.onnx`、`*.pt`、`*.pth`。

本轮没有创建`archive/`或`.runtime/`：当前授权要求Target只物化冻结Source Tree，并明确禁止创建runtime数据。后续如需新增结构，必须在独立阶段按批准范围形成新的可审计变更。

清单状态：`TARGET_MANIFEST_MATCHED`
