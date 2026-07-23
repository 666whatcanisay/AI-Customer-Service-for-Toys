# OPS-LAN-RECORD-FIX1 实现与验证

日期：2026-07-23

## 范围与根因

本任务只修改 Windows OPS 生命周期脚本和回归测试，不修改 A、B、C 的业务功能、API、模型、数据包、端口或网络策略。

LAN 启动包装器在 `Invoke-WithProcessEnvironment` 的环境变量循环中使用 `$name`。PowerShell 动态作用域使延迟执行的启动脚本块把该变量当作服务名，最终把运行记录写成 `CORS_ALLOWED_ORIGINS.json`、`VITE_RAG_API_BASE_URL.json` 等环境变量名。

## 修复

- `common_ai_customer_service.ps1` 统一使用 `$environmentVariableName` 保存和还原进程环境。
- `Start-ManagedServiceWithEnvironment` 显式捕获 `$serviceName` 及其启动参数，脚本块仅使用捕获值。
- `start_ai_customer_service.ps1` 在报告原异常前先输出已启动服务的安全摘要。
- 新增 `Test-OpsLanRecordFix1.ps1`；`Test-OpsT04Fix1.ps1` 的临时夹具与真实仓库 `.venv` 完全隔离，且能承受外部 PowerShell 的输出折行。

源分支提交为 `701b537` 和 `d78ebeb`；最终无冲突 squash 提交为 `56acf9792bf728eaad12f8025be658a6dcfdbbcc`，已推送至 `origin/develop`。

## 回归结果

正式 `develop` 已通过：

- `Test-OpsScripts.ps1`
- `Test-OpsT04Fix1.ps1`
- `Test-OpsRuntimeFix2.ps1`
- `Test-OpsLanMode.ps1`
- `Test-OpsLanRecordFix1.ps1`
- `scripts/windows` 全量 PowerShell 语法检查与 `git diff --check`

新增覆盖验证 `platform`、`rag`、`customer-web` 三个稳定记录名和正确字段；不生成环境变量名 JSON；正常/抛异常两种环境恢复；状态显示；记录篡改、未知端口和重复停止的拒绝/幂等行为。

## 旧进程安全 Gate

停止前证据保存于被忽略的 `.runtime/recovery-backup/ops-lan-record-fix1-prestop-20260723T092240Z.json`，SHA-256 为 `B8161EE377A65536ACA1986505DF0A00734B47A08EC3DC1BF6F8CF419A0523BC`。证据不包含密钥。

重新取证时，8000、8011、5173 均健康。8000 的记录 PID 可沿父子链对应监听进程，5173 的记录 PID 直接对应监听进程；8011 的 `platform` 记录已经被覆盖而不存在。8011 监听者的命令和父进程可确认其来自正式 C 虚拟环境，但没有可与之比较的历史记录启动时间。

按本任务的“任一身份项无法验证即不得停止”规则，未停止任何旧进程，未删除或移动任何现有运行记录，未执行新版 LAN 启动、状态/停止闭环或最终重新启动。系统尚未交给笔记本人工验收。
