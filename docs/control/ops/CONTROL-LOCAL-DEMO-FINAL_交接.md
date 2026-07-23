# CONTROL-LOCAL-DEMO-FINAL 交接

日期：2026-07-23

## 已完成

- 保护并移走了合并前主仓库未跟踪手册；仓库外备份为 `C:\Users\EDY\Documents\Codex\backups\CONTROL-LOCAL-DEMO-FINAL-20260723\本机启动与故障排查手册.main-untracked-before-merge.md`，SHA256 为 `2C89E42B408741958460A18A3EBF79FBCDA5033F2140AF4D6BD4C2FD3A0C05DB`。
- C 修复以 squash 提交 `2f997219a61c92439a3dddb6a923c7d8e282add1` 合入本地 `develop`；OPS 修复随后以 squash 提交 `ba03ec254619667a1072245198724fb9aecea426` 合入，无冲突。
- C 分支测试为 60 项通过（仅既有 `TestClient` 弃用警告）；OPS PowerShell 单测通过。
- 已验证本机忽略配置指向正式仓库和原始 V0.3.1 ZIP；ZIP SHA256 为 `B2E43A25F26EE4369A16F5730A2550E1BC0798CDC22F3029BA85FFCCD275F95D`。专用运行测试数据库尚未创建，未触碰任何既有数据库。

## 初始阻断（已解除）

正式 `scripts\windows\启动AI客服.bat` 在执行前的端口保护拒绝继续。`127.0.0.1:5173` 被 PID 35176 占用：

- 可执行文件：`C:\Users\EDY\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`
- 命令行：另一个项目 `C:\Users\EDY\Documents\Codex\2026-07-23\多多商家版聚合聊天\项目开发者` 的 Vite。
- 本项目 `.runtime` 没有该 PID 的登记。

本任务没有停止、强杀或修改该未知进程。用户释放 5173 后，已从正式主仓库执行 `scripts\windows\启动AI客服.bat`，没有手工补启任一服务。

## 最终本机验证

- Alembic 从空的专用运行库完成 `0001_ct02_ingestion` 与 `0002_ct02b_test_catalog`；状态脚本确认 revision 为 `0002_ct02b_test_catalog`。
- 原始 V0.3.1 ZIP 由配置直接提供给正式脚本，未修改原文件；源 SHA256 仍为 `B2E43A25F26EE4369A16F5730A2550E1BC0798CDC22F3029BA85FFCCD275F95D`。C 对原始字节的直接预检返回 HTTP 200、`can_import=true`，并识别 `PDD-SM-2026-001-TEST`、测试租户、禁生产和禁自动发送。
- C 已导入 1 家汕明店铺、5 个商品、18 个 SKU/组合和 28 个评测；A 同步记录为 47/47。`GET /health`、店铺和商品/SKU 接口均为 HTTP 200。
- CORS：来自 `http://127.0.0.1:5173` 的 GET 和 OPTIONS 均返回同源 `Access-Control-Allow-Origin`；未授权 Origin 没有该响应头。
- A `/api/health` 为 200，`ready=true`、`model_configured=true`、`initialization_error=null`。真实聊天返回带 3 个来源的 Ollama 回答，而非模型未配置或检索兜底。
- B `http://127.0.0.1:5173/` 为 HTTP 200。前端未配置覆盖值时，`platformClient` 的实际默认平台 API 为 `http://127.0.0.1:8011`。
- 正式状态脚本退出码为 0。受管启动记录 PID：C 7308、A 4256、B 26576；监听 worker PID：C 28160、A 16464、B 26576。三条 `.runtime` 记录均指向正式主仓库的工作目录和启动命令。

## 用户体验

服务当前保持运行。打开 `http://127.0.0.1:5173/`，选择汕明店铺并确认商品与 SKU 可见，再提问：“这个积木适合几岁儿童？安全注意事项有哪些？”。完成体验后，使用 `scripts\windows\停止AI客服.bat` 正常停止；不要关闭防火墙、强杀未知进程或提交本地配置、数据库、日志、测试数据和密钥。
