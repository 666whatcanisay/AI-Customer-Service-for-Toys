# AI-CS Windows Runtime Script Alignment Report V1

执行日期：2026-08-01

正式项目：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`

正式实现提交：`443cce0`（集成后运行验证提交：`d450597d2cb09493a291f894e7dac6a3f0150e56`）

旧目录兼容提交：`fbcba20`、`cd61f0cbcca4ea30a399f1ce21722bfb9f5d3497`

## 1. 旧脚本清单

完整逐文件审计见 [AI-CS Old Runtime Script Audit V1](./AI-CS-Old-Runtime-Script-Audit-V1.md)。旧目录共有 16 个原始 PowerShell 文件和 10 个 BAT：

- 13 个可执行 PowerShell 入口：启动、停止、状态、LAN、Admin、防火墙、诊断以及三套历史大写入口。
- 3 个内部历史资产：`common_ai_customer_service.ps1`、`Ops.Common.ps1`、`config.local.ps1`。
- 10 个中文 BAT：启动、停止、状态、LAN 状态、Admin、防火墙和诊断。

旧配置原先绑定旧 RepositoryRoot、旧 venv、旧 `.runtime` 和数据库路径，因此旧快捷方式存在启动旧代码的风险。旧内部文件未删除，但已经从全部操作入口调用链断开。

## 2. 迁移策略

```text
旧桌面快捷方式 / 旧 BAT
            │
            ▼
旧目录同名 PowerShell（只做兼容包装）
            │
            ▼
legacy_runtime_redirect.ps1
  ├─ 解析同级 AI-CS
  ├─ 校验 Git root / 目录名 / SHA
  ├─ 拒绝旧目录 ConfigPath
  └─ 显示“项目已迁移，请使用 AI-CS 目录”
            │
            ▼
AI-CS\scripts\windows\标准入口
            │
            ▼
.runtime\phase-e\config\green-standard.local.ps1
```

不删除旧脚本，不破坏已有快捷方式；旧目录只是兼容跳转入口，不再拥有 Runtime 身份。正式项目不包含旧仓库名称或旧绝对路径引用。

## 3. 修改文件

正式项目：

- 公共运行库：`common_ai_customer_service.ps1`。
- 标准入口：`start_ai_customer_service.ps1`、`stop_ai_customer_service.ps1`、`status_ai_customer_service.ps1`、`start_lan_ai_customer_service.ps1`、`status_lan_ai_customer_service.ps1`、`diagnose_lan_ai_customer_service.ps1`、`open_admin_web.ps1`、防火墙检查/配置入口。
- 历史大写入口：统一调用小写标准入口，不再形成第二套 Runtime。
- 5 个用户常用中文 BAT：统一 UTF-8 代码页、`ExecutionPolicy Bypass`、参数转发、退出码和失败后暂停。
- OPS 测试：配置优先级、RepositoryRoot、安全停止、目标 Pilot 静态边界和状态性能检查。

旧项目：

- 新增 `legacy_runtime_redirect.ps1`。
- 13 个 PowerShell 操作入口改成兼容包装器。
- 10 个中文 BAT 统一编码、参数、退出码和可见错误处理。
- 未修改旧业务代码、数据库、历史内部库或用户其他未提交修改。

## 4. 正式启动方式

日常操作只使用以下命令；无需手工传入配置，标准脚本优先解析 `green-standard.local.ps1`：

```powershell
cd C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS

.\scripts\windows\start_ai_customer_service.ps1
.\scripts\windows\status_ai_customer_service.ps1
.\scripts\windows\stop_ai_customer_service.ps1
```

LAN 显式入口：

```powershell
.\scripts\windows\start_lan_ai_customer_service.ps1
.\scripts\windows\diagnose_lan_ai_customer_service.ps1
```

Admin 可用性检查/打开入口：

```powershell
.\scripts\windows\open_admin_web.ps1
```

启动前输出并校验 RepositoryRoot、Git SHA、源码 CLEAN、配置路径、A/C Python、Node 和 pnpm。启动中任何后续服务失败时，只清理本轮已启动且身份匹配的服务。

## 5. 兼容与运行验证

| 验证项 | 结果 |
|---|---|
| 正式项目 PowerShell 语法 | PASS |
| Windows OPS 自动测试 | PASS，10/10 套 |
| 新目录 `stop` | PASS，四个受管服务安全停止，四端口释放 |
| 新目录 `start` | PASS，默认 Auto 恢复既有 LAN 模式 |
| 新目录 `status` | PASS，完整状态约 3 秒返回；原超过 90 秒风险已修复 |
| 重复 `start` | PASS，识别四服务已运行，不重复创建 |
| 显式 LAN 启动 | PASS，识别受控以太网和 LAN Runtime |
| 旧目录兼容 `start` | PASS，显示迁移提示并执行正式脚本 |
| 旧目录兼容 `status` | PASS，读取正式四服务，不读取旧 Runtime |
| B `192.168.1.11:5173` | HTTP 200 |
| Admin `127.0.0.1:5174` | HTTP 200 |
| A `127.0.0.1:8000/api/health` | HTTP 200 |
| C `127.0.0.1:8011/health` | HTTP 200 |

运行身份验证：

- `runtimeMode=standard`
- `networkMode=LAN`
- C API `8011`、A `8000`、B `5173`、Admin `5174` 均为 `RUNNING`。
- 数据库仍为 `0012_internal_production_finalization_v1`，未执行 migration。
- A active collection 仍为 `test_knowledge_v031`，56 chunks；未删除或重建向量数据。
- 最终交付 Runtime 从正式 release 分支 HEAD 启动；精确 SHA 以 Git HEAD 和四个受管运行记录共同为准。

## 6. 已关闭问题与剩余边界

- `BUG-OPS-003` 已关闭：无界 Windows CIM 进程查询改成有界查询，Admin 状态不再重复读取。
- 未配置、删除或放宽防火墙规则；第二台电脑的网络/VLAN可达性仍属于独立网络验收，不是本次脚本身份收敛范围。
- 旧工作区保留其他用户脏修改；兼容提交只包含 `scripts/windows/**`，没有清理或覆盖。

最终状态：`WINDOWS_RUNTIME_SCRIPT_ALIGNED_V1`。
