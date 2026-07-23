# CONTROL-LOCAL-DEMO-FINAL 交接

日期：2026-07-23

## 已完成

- 保护并移走了合并前主仓库未跟踪手册；仓库外备份为 `C:\Users\EDY\Documents\Codex\backups\CONTROL-LOCAL-DEMO-FINAL-20260723\本机启动与故障排查手册.main-untracked-before-merge.md`，SHA256 为 `2C89E42B408741958460A18A3EBF79FBCDA5033F2140AF4D6BD4C2FD3A0C05DB`。
- C 修复以 squash 提交 `2f997219a61c92439a3dddb6a923c7d8e282add1` 合入本地 `develop`；OPS 修复随后以 squash 提交 `ba03ec254619667a1072245198724fb9aecea426` 合入，无冲突。
- C 分支测试为 60 项通过（仅既有 `TestClient` 弃用警告）；OPS PowerShell 单测通过。
- 已验证本机忽略配置指向正式仓库和原始 V0.3.1 ZIP；ZIP SHA256 为 `B2E43A25F26EE4369A16F5730A2550E1BC0798CDC22F3029BA85FFCCD275F95D`。专用运行测试数据库尚未创建，未触碰任何既有数据库。

## 当前阻断

正式 `scripts\windows\启动AI客服.bat` 在执行前的端口保护拒绝继续。`127.0.0.1:5173` 被 PID 35176 占用：

- 可执行文件：`C:\Users\EDY\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`
- 命令行：另一个项目 `C:\Users\EDY\Documents\Codex\2026-07-23\多多商家版聚合聊天\项目开发者` 的 Vite。
- 本项目 `.runtime` 没有该 PID 的登记。

本任务没有停止、强杀或修改该未知进程。释放 5173 后，应从正式主仓库执行 `scripts\windows\启动AI客服.bat`，而不是手工补启任一服务；然后完成状态脚本、CORS、导入、A 模型和真实回答的最终 Gate。
