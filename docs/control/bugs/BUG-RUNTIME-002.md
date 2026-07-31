# BUG-RUNTIME-002 — Windows 通用启动入口与正式 LAN Runtime 错配

- 等级：P1
- 模块：OPS / Windows Runtime entrypoints
- 状态：OPEN
- 发现时间：2026-07-31
- 发现版本：`AI-CS@2ed20bde56e2498f5eb8daa94d62777c01b48258`

## 问题描述

正式四服务以 `runtimeMode=standard`、`networkMode=LAN` 运行时，执行：

```powershell
.\scripts\windows\start_ai_customer_service.ps1 `
  -ConfigPath ".runtime\phase-e\config\green-standard.local.ps1"
```

通用脚本仍按 LOCAL 地址检查 B。C、A、Admin 因回环地址相同被识别为健康，B 实际监听 `192.168.1.11:5173`，却被脚本按 `127.0.0.1:5173` 判为不健康，最终报“仅部分服务处于可信健康运行状态”。

中文 `.bat` 入口另有配置解析问题：它们不传 `ConfigPath`，默认查找 `scripts/windows/config.local.ps1`；该文件在正式 Monorepo 中不存在，正式配置位于 Git 忽略的 `.runtime/phase-e/config/green-standard.local.ps1`。因此双击启动、状态、停止和打开后台入口不能操作正式 Runtime。

## 影响

- 运营人员无法通过通用命令重复确认/启动当前正式 Runtime。
- 中文双击入口不能使用正式配置，表现为“没有作用”或短暂报错窗口。
- 服务本身没有停止或损坏；LAN 状态脚本证明四服务仍为同 SHA、健康运行。

## 根因

1. `start_ai_customer_service.ps1` 和 `status_ai_customer_service.ps1` 固定使用基础 LOCAL 配置，没有读取受管运行记录中的 `network_mode`。
2. `Get-LocalConfig` 只支持显式 `ConfigPath` 或旧版 `scripts/windows/config.local.ps1`，没有为 R008 后的唯一正式目录解析受控 `.runtime/phase-e/config/green-standard.local.ps1`。

## 修复边界

- 通用 start/status 增加 `Auto|Local|Lan` 模式；Auto 优先沿用同一正式仓库受管记录中的一致网络模式。
- 未显式传入配置且旧版本地配置不存在时，安全回退到仓库内正式 `.runtime/phase-e/config/green-standard.local.ps1`。
- 专用 LAN 启动/状态入口继续保留；停止、后台及中文 `.bat` 通过同一配置解析能力工作。
- 不修改 A/B/C 业务代码、UI、contracts、数据库、Prompt、模型、RAG 或网络防火墙。

## 验收标准

1. 正式 LAN 已运行时，通用 start 返回“已运行”，不再报部分服务。
2. 通用 status 自动显示 LAN 的 B 地址和健康状态。
3. 无 `scripts/windows/config.local.ps1` 时，中文 start/status/stop/admin 入口能找到正式配置。
4. 停止后通用 start 能沿用受管记录恢复同一 LAN Runtime；四服务同 SHA、standard/LAN、health PASS。
5. 失败启动仍只清理本轮已启动服务，不按端口强杀，不修改数据库或防火墙。
