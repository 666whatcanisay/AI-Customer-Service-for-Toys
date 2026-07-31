# AI-CS Runtime Entry Alignment Report V1

日期：2026-07-31

问题：`BUG-RUNTIME-002`

实现代码 SHA：`0eab157d7e53192ff5eae46d68d66b0ec25f8bae`

最终状态：`RUNTIME_ENTRY_ALIGNMENT_COMPLETE`

## 1. 结论

Windows 通用启动、状态和中文双击入口已与当前正式 Runtime 对齐。运营人员不再需要记住正式 `ConfigPath`，通用入口会安全解析 `AI-CS/.runtime/phase-e/config/green-standard.local.ps1`，并沿用最后一次成功运行的 `LOCAL` 或 `LAN` 模式。

当前正式模式保持 `runtimeMode=standard`、`networkMode=LAN`。A/C/Admin 仅监听本机回环，B 监听 `192.168.1.11:5173`。没有修改 A/B/C 业务代码、UI、contracts、数据库、Prompt、模型、RAG 数据或防火墙。

## 2. 原因

1. 通用 `start_ai_customer_service.ps1` 和 `status_ai_customer_service.ps1` 固定使用基础 LOCAL 配置。正式 B 实际运行于 LAN 地址时，脚本会把 C/A/Admin 判为健康、把 B 判为不健康，从而触发安全的“部分服务”拒绝。
2. 中文 `.bat` 不传 `ConfigPath`；旧默认文件 `scripts/windows/config.local.ps1` 不存在，而 R008 正式配置已经迁移到 Git 忽略的 `.runtime/phase-e/config/green-standard.local.ps1`。
3. 初版 Auto 修复在完全停止后仍会失去模式，因为服务记录会被安全停止流程删除。真实验收发现后，新增了不含密钥或业务数据的 Git 忽略网络模式偏好收据。

## 3. 修复内容

- `Get-LocalConfig`：显式配置优先；其次兼容旧 `config.local.ps1`；最后只在当前仓库内解析正式 `.runtime` 配置。
- 通用 start/status：新增 `-Mode Auto|Local|Lan`，默认 `Auto`。
- Auto：优先读取同仓库、一致的受管服务记录；完全停止后读取 `.runtime/phase-e/green-standard/network-mode.preference.json`；记录混合、损坏或指向其他仓库时拒绝执行。
- LOCAL/LAN 成功启动或可信重复启动后，保存 `ai-cs-runtime-network-mode.v1` 收据。收据只含仓库根、网络模式和时间，不含密钥、命令行、客户数据或业务数据。
- `start_target_pilot.ps1` 将选定模式传给标准启动和 readiness 检查。
- `启动AI客服.bat`、`检查AI客服状态.bat`、`启动客服试运行.bat` 显式使用 Auto；专用 LAN 入口继续保留。

## 4. 验证

### 隔离回归

以下 6 组 OPS 测试通过：

- `Test-OpsRuntimeEntryAlignment.ps1`
- `Test-OpsRuntimeFix2.ps1`
- `Test-OpsLanMode.ps1`
- `Test-OpsTargetPilotReady.ps1`
- `Test-OpsAdminWebT05.ps1`
- `Test-OpsScripts.ps1`

覆盖：配置优先级、模式偏好、混合/外部记录拒绝、部分启动清理、LAN 网卡边界、Admin PID 防篡改、中文入口和 PowerShell 语法。

### 正式真实验收

1. 候选脚本对已运行 LAN Runtime 执行用户原命令，返回“局域网 AI 客服已运行”，不再报部分服务。
2. 执行无 `ConfigPath` 的受管 stop，四端口全部释放。
3. 确认 LAN 偏好收据仍存在，再执行无 `ConfigPath` 的通用 start；四服务恢复为 LAN。
4. 无 `ConfigPath` 的通用 status 自动进入 LAN 状态页。
5. 通过 `cmd.exe` 真实执行 `启动AI客服.bat` 和 `检查AI客服状态.bat`；两者退出码为 0。
6. `open_admin_web.ps1 -NoLaunch` 无配置路径检查通过。

正式验收采样：

| 服务 | 地址 | Managed PID | Listener PID | 状态 |
| --- | --- | ---: | ---: | --- |
| C API | `127.0.0.1:8011` | 38768 | 18632 | RUNNING / health |
| A AI | `127.0.0.1:8000` | 11896 | 27364 | RUNNING / ready |
| B 客服 | `192.168.1.11:5173` | 6972 | 6972 | RUNNING / HTTP 200 |
| C Admin | `127.0.0.1:5174` | 35512 | 14992 | RUNNING / HTTP 200 |

四项均为 SHA `0eab157`、source CLEAN、standard/LAN。A 为 `ready=true`、`model_configured=true`、活动集合 `test_knowledge_v031=47`。C/B 客服目录各返回 1 个可用店铺，Admin HTTP 200。数据库保持 `0010_customer_available_catalog_v1`、`integrity_check=ok`。

## 5. 日常使用

在 `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS` 中执行：

```powershell
.\scripts\windows\start_ai_customer_service.ps1
.\scripts\windows\status_ai_customer_service.ps1
.\scripts\windows\stop_ai_customer_service.ps1
```

也可以双击：

- `启动AI客服.bat`
- `检查AI客服状态.bat`
- `停止AI客服.bat`
- `打开运营后台.bat`

通常不需要传 `ConfigPath`。需要强制切换时才使用 `-Mode Local` 或 `-Mode Lan`；Auto 会保持最后一次成功模式。不要删除 `.runtime` 网络模式偏好、PID 记录、数据库或向量数据，也不要按端口强杀进程。

最终状态：`RUNTIME_ENTRY_ALIGNMENT_COMPLETE`
