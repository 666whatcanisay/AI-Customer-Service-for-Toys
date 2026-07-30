# AI-CS Runtime Handover Report V1

> 文档类型：AI-CS当前正式运行交接
>
> 适用对象：未来开发者、维护者及项目负责人
>
> 交接日期：2026-07-30（Asia/Shanghai）
>
> 当前运行版本：`AI-CS@26f8cde1e8f7373315baa1ac68d02f7823b4de82`
>
> 交接状态：`RUNTIME_HANDOVER_READY`

## 0. 使用原则

本报告描述当前这台机器上的正式本地Pilot运行方式，不是公网生产部署手册。日常运行、开发和排错只以`AI-CS/`为主项目目录；Recovery只用于受控回滚，不能作为第二个开发目录。

本轮只生成交接文档并只读复核运行状态，没有停止、启动或重启服务，没有修改Target代码、UI、contracts、数据库或`.runtime`。

## 1. 当前唯一项目目录

唯一日常开发与运行目录：

```text
C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS
```

当前身份：

| 项目 | 当前值 |
| --- | --- |
| Branch | `control/r008-physical-migration-v1` |
| SHA | `26f8cde1e8f7373315baa1ac68d02f7823b4de82` |
| Contracts | `0.2.0` |
| Git状态 | `CLEAN` |
| Runtime配置 | `.runtime/phase-e/config/green-standard.local.ps1` |
| Runtime记录 | `.runtime/phase-e/green-standard/*.json` |

规则：

- 日常命令必须从该目录执行，并显式使用`green-standard.local.ps1`。
- 不得回到旧A/B/C Worktree或Recovery目录继续开发。
- 当前服务运行期间不要直接切分支、pull、checkout或编辑Target源码；这会使运行SHA与工作树事实失配，并可能被Vite热更新带入Pilot。
- R008 Phase F完成前，旧目录虽然仍可能物理存在，但不再是日常项目入口。

## 2. 日常启动方式

### 2.1 启动前检查

1. 使用专用的新PowerShell窗口。
2. 确认Ollama已运行且本机存在`qwen3.5:9b`；启动脚本不会自动下载模型。
3. 确认Target仍是批准的branch/SHA且工作树clean。
4. 先运行第4节状态命令；若四服务已全部`RUNNING`，不要重复启动。
5. 不要删除`.runtime`、`.venv`或`node_modules`。

### 2.2 标准启动命令

当前Target独立数据库、知识和向量路径必须通过标准配置及进程环境共同固定。请完整执行以下命令，不要只运行无`-ConfigPath`的默认启动：

```powershell
$aiCsRoot = 'C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS'
$standardConfig = Join-Path $aiCsRoot '.runtime\phase-e\config\green-standard.local.ps1'

Set-Location -LiteralPath $aiCsRoot

$env:KNOWLEDGE_BASE_PATH = Join-Path $aiCsRoot '.runtime\phase-e\standard-rag\knowledge-base'
$env:VECTOR_DB_PATH = Join-Path $aiCsRoot '.runtime\phase-e\standard-rag\vector-db'
$env:LOG_DIR = Join-Path $aiCsRoot '.runtime\phase-e\green-standard\app-logs'
$env:PLATFORM_KNOWLEDGE_MATERIAL_STORAGE_DIR = Join-Path $aiCsRoot '.runtime\phase-e\standard-knowledge-materials'
$env:VITE_RAG_API_BASE_URL = 'http://127.0.0.1:8000'
$env:VITE_PLATFORM_API_BASE_URL = 'http://127.0.0.1:8011'
$env:VITE_AI_API_BASE_URL = 'http://127.0.0.1:8000'
$env:PYTHONDONTWRITEBYTECODE = '1'

& powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File (Join-Path $aiCsRoot 'scripts\windows\start_ai_customer_service.ps1') `
  -ConfigPath $standardConfig
```

启动顺序由脚本固定为：

```text
C API 8011
↓
A 8000
↓
B 5173
↓
C Admin 5174
```

启动命令会执行受管身份、依赖、端口、C migration、health、A ready和合成AI smoke检查。任一步失败时不要按端口强杀，应查看启动失败摘要和受管记录。

建议该PowerShell只用于本次启动；服务启动完成后可以关闭窗口，已启动子进程会保留其环境。

## 3. 停止方式

使用Target受管停止脚本：

```powershell
$aiCsRoot = 'C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS'
$standardConfig = Join-Path $aiCsRoot '.runtime\phase-e\config\green-standard.local.ps1'

& powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File (Join-Path $aiCsRoot 'scripts\windows\stop_ai_customer_service.ps1') `
  -ConfigPath $standardConfig
```

脚本按以下顺序停止：

```text
C Admin
↓
B
↓
A
↓
C API
```

停止规则：

- 只停止与Target受管记录匹配的managed PID和listener PID。
- 禁止使用`Stop-Process`、任务管理器批量结束、按端口强杀或删除运行记录。
- 不要停止Ollama；它不属于这四个AI-CS服务的停止范围。
- 停止完成后运行第4节状态命令复核四服务均无Target受管运行记录。

## 4. 状态检查方式

官方状态命令：

```powershell
$aiCsRoot = 'C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS'
$standardConfig = Join-Path $aiCsRoot '.runtime\phase-e\config\green-standard.local.ps1'

& powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File (Join-Path $aiCsRoot 'scripts\windows\status_ai_customer_service.ps1') `
  -ConfigPath $standardConfig
```

正常运行时必须同时满足：

| 检查项 | 期望结果 |
| --- | --- |
| C | `RUNNING`，8011监听，health可用，revision `0008_customer_feedback_loop_v1` |
| A | `RUNNING`，8000监听，`ready=true`、`model_configured=true`、47 chunks |
| B | `RUNNING`，5173监听，页面health可用 |
| Admin | `RUNNING`，5174监听，页面health可用 |
| 运行身份 | 四服务均显示SHA `26f8cde...`、源码`CLEAN`、仓库版本身份已验证 |
| 网络 | 当前均绑定`127.0.0.1`；不是LAN模式 |

不要仅凭HTTP 200或端口监听认定服务正确；必须同时核对受管PID、监听PID、工作目录、SHA和源码状态。

## 5. 四服务说明

| 服务 | 端口 | 目录 | 责任 |
| --- | ---: | --- | --- |
| B 客服工作台 | 5173 | `frontend/` | 客服选择店铺/商品/SKU、输入问题、查看并人工确认AI建议；不自动发送 |
| C Admin | 5174 | `admin_web/` | 运营查看商品知识、资料、FAQ、安全规则、缺口、AI问题与只读AI状态 |
| A AI能力层 | 8000 | `backend/` | RAG检索、模型调用、建议回答、只读AI控制面；不执行业务动作 |
| C Platform API | 8011 | `platform_backend/` | C业务数据、目录、知识运营、反馈闭环和SQLite持久化Provider |

附属依赖：Ollama运行于`127.0.0.1:11434`，当前模型为`qwen3.5:9b`。Ollama不是第五个AI-CS受管服务，不应由AI-CS停止脚本关闭。

## 6. B客服体验入口

本机入口：

```text
首页：http://127.0.0.1:5173/
AI客服：http://127.0.0.1:5173/ai-chat
```

正常体验路径：

```text
确认测试客服
↓
选择店铺
↓
选择商品
↓
可选SKU
↓
输入不含隐私的测试问题
↓
生成建议
↓
人工核对后决定是否复制
```

页面必须持续显示“仅供建议、禁止自动发送、禁止自动退款、禁止修改订单”等边界。当前5173只绑定本机回环地址；R007公司网络/VLAN问题尚未关闭，不能把本机可用写成局域网已可用。

## 7. C运营体验入口

本机入口：

```text
运营首页：http://127.0.0.1:5174/overview
AI控制中心：http://127.0.0.1:5174/ai-capabilities
```

主要入口包括：店铺管理、商品知识中心、商品知识维护、知识缺口、知识资料、FAQ、安全规则、导入中心、客服运营工作台和AI问题中心。

当前Admin只绑定`127.0.0.1`，不对LAN开放；页面AI请求指向8000，Platform请求指向8011。Admin不提供自动发送、订单修改、退款、ERP写入、模型切换或Prompt修改。

## 8. 数据库位置说明

当前正式C数据库：

```text
C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS\.runtime\phase-e\data\standard-platform.sqlite3
```

相关运行数据：

```text
A知识：AI-CS\.runtime\phase-e\standard-rag\knowledge-base
A向量：AI-CS\.runtime\phase-e\standard-rag\vector-db
C资料：AI-CS\.runtime\phase-e\standard-knowledge-materials
运行记录/日志：AI-CS\.runtime\phase-e\green-standard
保护manifest：AI-CS\.runtime\phase-e\manifests
```

数据规则：

- `.runtime/**`全部Git忽略，不得提交、压缩进Git或复制到`archive/`。
- 不得删除、清空、重建或用测试空库覆盖`standard-platform.sqlite3`。
- C运行期间不要用普通文件复制替代SQLite一致性备份。
- 需要备份时，先确认任务授权，再使用`backup_target_pilot_data.ps1 -ConfirmBackup`和同一`green-standard`配置；不要手工复制正在写入的SQLite。
- 不在文档、日志或提交中记录客户内容、知识正文、密钥或真实对话。

## 9. Recovery回滚说明

Recovery目录：

```text
C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-pilot-baseline-recovery-v1
```

Recovery身份：

```text
SHA：cbc77ed883cb99e2eff76ccb8eb3193bbddaba38
状态：STOPPED_PRESERVED_ROLLBACK_ANCHOR
```

主要保护资产：

```text
原数据库：Recovery\.runtime\data\pilot-baseline-recovery-platform.sqlite3
最终在线备份：Recovery\.runtime\pilot-backups\platform-20260730-133209.sqlite3
原知识/向量：Recovery\backend\knowledge_base、Recovery\backend\vector_db
原配置：Recovery\scripts\windows\config.local.ps1
```

Recovery不是日常启动选项。只有在Target出现核心故障并获得明确回滚授权后，才执行：

1. 建立人工静默窗口，确认是否已有Target新业务写入。
2. 如已有写入，先备份Target并制定数据协调方案；禁止直接回退旧数据库。
3. 使用第3节Target官方停止命令停止四服务并确认标准端口释放。
4. 打开全新的PowerShell窗口，避免继承Target的RAG/数据库环境变量。
5. 从Recovery目录使用其`config.local.ps1`启动C→A→B→Admin。
6. 用Recovery状态脚本核对SHA、PID、revision 0008、47 chunks和页面。

禁止Target与Recovery同时占用5173、5174、8000、8011。Phase F和回滚保留决策完成前，不得移动、改名或删除Recovery。

## 10. 禁止事项

- 禁止从旧A/B/C Worktree或Recovery继续日常开发。
- 禁止在Target服务运行时直接切分支、pull、checkout或修改源码。
- 禁止省略`green-standard.local.ps1`，也禁止让A回退到默认知识/向量目录。
- 禁止按端口强杀、停止未知PID、删除或伪造运行记录。
- 禁止提交`.env`、`.runtime`、数据库、知识源、向量、日志、模型、依赖、构建产物或客户数据。
- 禁止重建/清空数据库、用测试字段替代业务状态或修改contracts而不经过Interface Freeze。
- 禁止自动发送、自动退款、订单/ERP写入、自动发布知识、自动修改Prompt或自动训练。
- 禁止把本机5173/5174可用解释为公司网络已可访问。
- 禁止把Runtime迁移完成解释为R006、R003或R005已经验收。
- 禁止在未授权Phase F前删除Recovery或处理旧Worktree。

## 11. 当前交接结论

当前唯一日常项目入口、四服务命令、数据路径、体验入口和回滚锚点均已形成可复核说明。当前Runtime保持运行且未被本轮修改。

```text
RUNTIME_HANDOVER_READY
TARGET_STANDARD_RUNTIME_ACTIVE
RECOVERY_ROLLBACK_ONLY
PHASE_F_NOT_AUTHORIZED
```

最终状态：`RUNTIME_HANDOVER_READY`
