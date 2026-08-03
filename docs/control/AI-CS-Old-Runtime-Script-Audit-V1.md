# AI-CS Old Runtime Script Audit V1

审计时间：2026-08-01

旧目录：`C:\Users\EDY\Documents\Codex\2026-07-21\666whatcanisay-ai-customer-service-for-toys`

审计基线：`codex/agent-system-foundation-v1@e2489ab9c65ad45600a9bcdcb643763c97d97b4f`

## 结论

旧目录原有中文 BAT 都通过 `%~dp0` 调用同目录 PowerShell，13 个操作入口继续加载旧目录配置或旧 OPS 库，因此旧快捷方式可能启动旧代码。旧 `config.local.ps1` 明确绑定旧 RepositoryRoot、旧 Python 环境和旧 `.runtime`；这是迁移后运行身份分裂的直接风险。

兼容收敛后，13 个操作入口不再加载旧 `config.local.ps1`、`common_ai_customer_service.ps1` 或 `Ops.Common.ps1`，统一经 `legacy_runtime_redirect.ps1` 调用同级工作区的 `AI-CS\scripts\windows`。旧内部库和配置仅作为历史兼容资产保留，不删除、不执行。

## PowerShell 清单

| 脚本 | 原作用 | 原调用/路径依赖 | 收敛结果 |
|---|---|---|---|
| `start_ai_customer_service.ps1` | 通用启动 C/A/B/Admin | 加载旧 common/config，使用旧 RepositoryRoot | 跳转正式同名入口 |
| `start_lan_ai_customer_service.ps1` | LAN 启动 | 加载旧 common/config | 跳转正式同名入口 |
| `status_ai_customer_service.ps1` | 通用状态 | 加载旧 common/config | 跳转正式同名入口 |
| `status_lan_ai_customer_service.ps1` | LAN 状态 | 加载旧 common/config | 跳转正式同名入口 |
| `stop_ai_customer_service.ps1` | 安全停止 | 加载旧 common/config | 跳转正式同名入口 |
| `open_admin_web.ps1` | 打开 Admin | 加载旧 common/config | 跳转正式同名入口 |
| `diagnose_lan_ai_customer_service.ps1` | LAN 诊断 | 加载旧 common/config | 跳转正式同名入口 |
| `check_ai_customer_firewall.ps1` | 防火墙只读检查 | 加载旧 common/config | 跳转正式同名入口 |
| `configure_ai_customer_firewall.ps1` | 配置受控防火墙规则 | 加载旧 common/config | 跳转正式同名入口 |
| `remove_ai_customer_firewall_rule.ps1` | 删除受控防火墙规则 | 加载旧 common/config | 跳转正式同名入口 |
| `Start-AICustomerService.ps1` | 早期 OPS 启动入口 | 加载旧 `Ops.Common.ps1` | 跳转正式标准启动入口 |
| `Stop-AICustomerService.ps1` | 早期 OPS 停止入口 | 加载旧 `Ops.Common.ps1` | 跳转正式标准停止入口 |
| `Get-AICustomerServiceStatus.ps1` | 早期 OPS 状态入口 | 加载旧 `Ops.Common.ps1` | 跳转正式标准状态入口 |
| `common_ai_customer_service.ps1` | 旧版标准脚本公共库 | 旧 RepositoryRoot 的间接依赖 | 历史保留；操作入口不再引用 |
| `Ops.Common.ps1` | 更早 OPS 公共库 | 以旧仓库为脚本根 | 历史保留；操作入口不再引用 |
| `config.local.ps1` | 旧本机运行配置 | 硬编码旧 RepositoryRoot、venv、runtime、SQLite | 历史保留；操作入口不再引用 |

新增兼容基础设施：`legacy_runtime_redirect.ps1`。它从旧仓库的父目录解析唯一同级 `AI-CS`，校验目标 Git root、目录名和 SHA，拒绝转发旧目录配置，再执行正式脚本。

## BAT 清单与调用关系

| BAT | 调用的旧兼容包装器 | 最终正式入口 |
|---|---|---|
| `启动AI客服.bat` | `start_ai_customer_service.ps1` | `AI-CS\...\start_ai_customer_service.ps1` |
| `停止AI客服.bat` | `stop_ai_customer_service.ps1` | `AI-CS\...\stop_ai_customer_service.ps1` |
| `检查AI客服状态.bat` | `status_ai_customer_service.ps1` | `AI-CS\...\status_ai_customer_service.ps1` |
| `启动局域网客服.bat` | `start_lan_ai_customer_service.ps1` | `AI-CS\...\start_lan_ai_customer_service.ps1` |
| `检查局域网客服状态.bat` | `status_lan_ai_customer_service.ps1` | `AI-CS\...\status_lan_ai_customer_service.ps1` |
| `打开运营后台.bat` | `open_admin_web.ps1` | `AI-CS\...\open_admin_web.ps1` |
| `诊断AI客服局域网.bat` | `diagnose_lan_ai_customer_service.ps1` | `AI-CS\...\diagnose_lan_ai_customer_service.ps1` |
| `检查AI客服防火墙.bat` | `check_ai_customer_firewall.ps1` | `AI-CS\...\check_ai_customer_firewall.ps1` |
| `配置AI客服防火墙.bat` | `configure_ai_customer_firewall.ps1` | `AI-CS\...\configure_ai_customer_firewall.ps1` |
| `删除AI客服防火墙规则.bat` | `remove_ai_customer_firewall_rule.ps1` | `AI-CS\...\remove_ai_customer_firewall_rule.ps1` |

全部 BAT 使用 `chcp 65001`、`powershell.exe -NoProfile -ExecutionPolicy Bypass`、参数转发、退出码保留和 `pause`，避免错误后黑屏退出。

## 风险边界

- 不删除旧脚本和旧配置，已有桌面快捷方式仍可继续使用。
- 旧仓库仍有用户未提交代码和文档；本次未整理、未覆盖。
- 旧 `config.local.ps1` 仍含历史路径，但已从所有操作入口调用链断开；不得手工将其作为正式 `-ConfigPath` 转发。
- 正式项目脚本中不存在旧仓库名称或旧绝对路径引用。

审计结论：`OLD_RUNTIME_SCRIPT_AUDIT_COMPLETE`。
