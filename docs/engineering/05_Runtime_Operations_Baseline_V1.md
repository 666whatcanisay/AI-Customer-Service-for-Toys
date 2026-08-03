# AI-CS Runtime Operations Baseline V1

## 1. 正式运行身份

| 项目 | 基线值 |
|---|---|
| Repository Root | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS` |
| Git SHA | `860d102059cab00ee946512478807f8a8d6efae9` |
| Runtime mode | `standard` |
| Network mode | `LAN`（由受管记录/持久偏好解析） |
| Runtime config | `.runtime/phase-e/config/green-standard.local.ps1` |
| Runtime records/logs | `.runtime/phase-e/green-standard/` |
| Database revision | `0012_internal_production_finalization_v1` |
| Active RAG collection | `test_knowledge_v031`，56 chunks |
| Model | `qwen3.5:9b`，ready |

证据采集于2026-08-03受控重启后。PID是易变运行证据，不是配置常量。

## 2. 四服务

| 服务 | 源码 | 端口/绑定 | Health | 启动进程 |
|---|---|---|---|---|
| C Platform API | `platform_backend/` | `127.0.0.1:8011` | `/health` | Python/uvicorn |
| A AI Service | `backend/` | `127.0.0.1:8000` | `/api/health`、`/api/status` | Python/uvicorn |
| B Customer Client | `frontend/` | `192.168.1.11:5173`（当前LAN） | `/` | Node/Vite |
| C Admin | `admin_web/` | `127.0.0.1:5174` | `/` | pnpm/Vite |

当前受管PID快照：

| 服务 | Managed PID | Listener PID |
|---|---:|---:|
| C | 8284 | 30440 |
| A | 25564 | 19624 |
| B | 19912 | 19912 |
| Admin | 29648 | 26192 |

当前四份record位于：

- `.runtime/phase-e/green-standard/platform.json`
- `.runtime/phase-e/green-standard/rag.json`
- `.runtime/phase-e/green-standard/customer-web.json`
- `.runtime/phase-e/green-standard/admin-web.json`

记录包含Repository Root、Git SHA、source state/fingerprint、runtime/network mode、managed/listener PID、工作目录和health URL。不得手工改record绕过检查。

## 3. 日常命令

```powershell
cd C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS

.\scripts\windows\start_ai_customer_service.ps1
.\scripts\windows\status_ai_customer_service.ps1
.\scripts\windows\stop_ai_customer_service.ps1
```

中文入口仍可用：

- `scripts/windows/启动AI客服.bat`
- `scripts/windows/检查AI客服状态.bat`
- `scripts/windows/停止AI客服.bat`
- `scripts/windows/启动局域网客服.bat`
- `scripts/windows/诊断AI客服局域网.bat`

这些入口最终调用同目录PowerShell，并使用`ExecutionPolicy Bypass`。不要从历史项目目录启动。

## 4. 配置解析

无`-ConfigPath`时，`Resolve-AiCustomerServiceConfigPath`优先选择正式：

```text
.runtime/phase-e/config/green-standard.local.ps1
```

证据：`scripts/windows/common_ai_customer_service.ps1:4-11`。标准Runtime还会校验配置确实来自正式AI-CS根目录，见`:16-45`。

当前非敏感配置事实：

| 配置 | 值 |
|---|---|
| `RuntimeMode` | `standard` |
| `RagPort` | 8000 |
| `PlatformPort` | 8011 |
| `CustomerWebPort` | 5173 |
| `AdminWebPort` | 5174 |
| A/C默认Bind | 127.0.0.1 |
| Admin Bind | 127.0.0.1 |
| LAN B Bind | 当前受管地址192.168.1.11 |
| `AutoImportTestData` | false |
| `AutoSyncTestKnowledge` | false |
| `RagActiveCollectionName` | `test_knowledge_v031` |
| `OllamaModel` | `qwen3.5:9b` |

静态配置中的LAN布尔值不是最终运行模式的唯一来源；通用入口会优先保留受管record或`.runtime`网络偏好。以`status_ai_customer_service.ps1`输出为准。

## 5. 启动流程

通用start入口：`scripts/windows/start_ai_customer_service.ps1`。

1. 解析正式配置和LOCAL/LAN有效模式；
2. 校验Repository Root、配置路径、Git身份、Python/Node/pnpm；
3. 拒绝混合/不可信已有服务；
4. LAN模式转到`start_lan_ai_customer_service.ps1`；
5. 启动C Platform API；
6. 启动A并等待RAG/model ready；
7. 启动B；
8. 启动Admin；
9. 写入四份受管记录；
10. 执行health、active collection与AI smoke；
11. 若后续组件失败，清理本次已经启动的组件，避免半启动。

正式配置禁止自动导入测试包和自动同步知识，因此正常重启不应修改业务数据或重建RAG。

## 6. 停止流程

`stop_ai_customer_service.ps1`按受管记录验证进程身份，只停止可信进程。受控顺序为：

```text
Admin → B → A → C
```

停止后应确认5174、5173、8000、8011全部释放。不要使用按端口强杀或全局结束Node/Python进程替代正式stop脚本。

## 7. 状态与身份判定

`status_ai_customer_service.ps1`检查：

- Managed PID与Listener PID；
- 端口监听和health；
- Repository Root；
- 当前Git SHA；
- source state与source fingerprint；
- runtimeMode；
- networkMode记录；
- database revision；
- active/available collections与chunks；
- model configured/ready。

Runtime身份PASS条件：

```text
repositoryRoot=True
gitSha=True
sourceFingerprint=True
runtimeMode=True
networkModeRecorded=True
```

实现：`scripts/windows/common_ai_customer_service.ps1:962-980`及`status_*`脚本。

如果工作区新增未提交文档或代码，source fingerprint会失败；不得关闭检查或手工改record。正确方式是形成受控提交，再在静默窗口重启到同一SHA。

## 8. 健康检查

### 8.1 标准状态

```powershell
.\scripts\windows\status_ai_customer_service.ps1
```

### 8.2 HTTP只读检查

```powershell
Invoke-WebRequest http://127.0.0.1:8011/health -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8000/api/health -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8000/api/status -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:5174/ -UseBasicParsing
Invoke-WebRequest http://192.168.1.11:5173/ -UseBasicParsing
```

### 8.3 数据库只读健康

```powershell
.\scripts\database-health-check\Invoke-AICustomerDatabaseHealthCheck.ps1 `
  -DatabasePath '.runtime\phase-e\data\standard-platform.sqlite3' `
  -ExpectedRevision '0012_internal_production_finalization_v1' `
  -Compact
```

### 8.4 LAN诊断

```powershell
.\scripts\windows\diagnose_lan_ai_customer_service.ps1
```

LAN诊断只报告网卡、地址、端口和防火墙；业务代码不能解决公司VLAN或端口策略。

## 9. 数据与日志位置

| 资产 | 位置 | Git |
|---|---|---|
| SQLite | `.runtime/phase-e/data/standard-platform.sqlite3` | 禁止 |
| Chroma | `.runtime/phase-e/standard-rag/vector-db` | 禁止 |
| A知识目录 | `.runtime/phase-e/standard-rag/knowledge-base` | 禁止 |
| C资料目录 | `.runtime/phase-e/standard-knowledge-materials` | 禁止 |
| Runtime records/logs | `.runtime/phase-e/green-standard` | 禁止 |
| Ollama模型 | 用户本机Ollama存储 | 禁止 |

日志默认位于`.runtime/phase-e/green-standard/logs`。报告中只能引用错误摘要、PID、状态和hash，不提交原始日志或客户内容。

## 10. 受控重启Runbook

1. 确认人工静默窗口；
2. `git status --porcelain`必须为空；
3. 记录branch、HEAD、当前PID和status；
4. 运行数据库健康检查并记录revision、计数；
5. 记录active collection、chunks和model ready；
6. 执行正式stop；
7. 确认四端口释放；
8. 如需文件hash，在停机后计算SQLite离线hash；
9. 执行正式start；
10. 执行status和四HTTP检查；
11. 比对SHA、fingerprint、database、RAG和model；
12. 服务保持运行并保存脱敏证据。

Windows运行中的SQLite可能因C持有文件句柄而拒绝直接`Get-FileHash`；不要强制复制锁定文件。应先使用在线只读健康检查，必要时在受控stop后计算离线hash。

## 11. 故障处置

| 现象 | 处理 |
|---|---|
| `sourceFingerprint=False` | 停止发布；审计Git dirty，不绕过；受控提交并重启 |
| 只有部分服务可信运行 | 先status核对record/PID；不要叠加启动 |
| C/A启动后B/Admin失败 | start脚本应清理本次启动项；检查对应日志后重新完整启动 |
| 数据库revision异常 | 停止；不自动migration；恢复备份或由DB Owner评审 |
| active collection无chunks | 输出知识warning；不删除向量、不全量重建；核对配置与发布记录 |
| 5173服务器正常、其他电脑不可达 | 运行LAN诊断，检查Private网络/防火墙/VLAN；不改业务代码 |
| 未知进程占端口 | 不强杀；记录PID、命令和工作目录，确认所有权后处理 |

## 12. 回滚原则

- 代码回滚、数据库恢复、RAG恢复是三条独立轨道；
- 纯代码/文档发布失败且数据库未变：恢复旧Git SHA并按标准脚本重启；
- 发生数据库写入前必须已有在线备份和离线回滚快照；禁止直接downgrade破坏业务历史；
- RAG发布失败保留上一fingerprint版本，禁止全量删除collection；
- Recovery目录只作为回滚锚点，不重新成为日常开发目录。
