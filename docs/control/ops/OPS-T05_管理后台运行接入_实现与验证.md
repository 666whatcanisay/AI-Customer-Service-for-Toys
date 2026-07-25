# OPS-T05 管理后台运行接入

日期：2026-07-24

范围：`scripts/windows/**`、`docs/control/**`。未修改 `admin_web/**`、A/B/C 业务代码、共享 contracts、依赖或防火墙规则。

## 交付

- `config.local.ps1.example` 与本地配置解析增加 `AdminWebPort=5174`、`AdminWebBindAddress=127.0.0.1`、`AdminWebUrl=http://127.0.0.1:5174/`、`AdminEnableLanMode=false` 和 `AdminOpenBrowser=false`；旧的被忽略本地配置缺少这些字段时获得相同安全默认值。
- 本机与 LAN 客服启动器均按 C → A → B → Admin 顺序编排。Admin 通过 `pnpm dev --host ... --port ... --strictPort` 调用 `admin_web/package.json` 的真实 `dev` script，且只在 Admin URL 返回 HTTP 成功后登记为启动成功。
- 启动前检查 Node、pnpm、`admin_web/package.json`、`pnpm-lock.yaml`、`node_modules` 和 5174；未知监听者会阻断启动，绝不按端口结束。
- `.runtime/admin-web.json` 记录服务名、受管 PID、监听 PID、父 PID、创建/启动时间、可执行路径、命令摘要、工作目录、绑定地址、端口和 URL；另保存监听进程路径与启动时间以应对 pnpm 在 Windows 上分离子进程的实现细节。
- 状态和只读 LAN 诊断新增 Admin 页面、5174、监听 PID、URL、LAN 暴露标志、日志与依赖目录存在性；A/C health 和 B 入口仍保留。
- 停止器只在受管 PID、监听 PID、路径、启动时间、命令特征、端口和运行记录一致时停止 Admin 进程树；篡改 PID 或未知端口均拒绝。新增 `打开运营后台.bat`，仅在页面可用时由服务器本机显式打开默认浏览器。

## 验证

- `Test-OpsAdminWebT05.ps1`：通过。隔离的真实 pnpm `dev` script 验证缺少 `admin_web`、缺少 `node_modules`、未知端口、正常启动、重复启动、状态、打开检查、运行记录字段、安全停止、重复停止和伪造 PID 拒绝。
- 既有 `Test-OpsRuntimeFix2.ps1`、`Test-OpsLanRecordFix1.ps1`、`Test-OpsLanMode.ps1`、`Test-OpsT04Fix1.ps1`、`Test-OpsScripts.ps1` 和全量 PowerShell 语法检查均通过。
- `git diff --check` 通过；变更仅位于允许目录。

## 环境结论与交接

当前隔离 Worktree 中 `admin_web/package.json` 与 `pnpm-lock.yaml` 存在，但 `admin_web/node_modules` 不存在。按“不安装依赖”边界，未运行真实 A/C/B/Admin 闭环，也没有占用 5174、停止现有服务或打开浏览器。待目标服务器人工准备 Admin 依赖后，执行：启动 → 状态 → 停止 → 再启动；默认应只监听并访问 `http://127.0.0.1:5174/`。

`AdminEnableLanMode=true` 不是防火墙授权。本轮仍不开放 5174，不创建或修改任何防火墙规则。
