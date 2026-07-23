# Git 与分支状态

- 正式远端：`https://github.com/666whatcanisay/AI-Customer-Service-for-Toys.git`。
- PR #3：`agent/rag-core` → `develop`，Head `52e4325`，2026-07-22 09:00:14 +08:00 squash merge 为 `6284fcd014262427603338295d9fc13a757851f9`。
- B 第一次 rebase：无冲突，Head 更新为 `12a2c99eb547c531b34622b83f5f24bbeb4e7cff`。
- C 第一次 rebase：无冲突，Head 更新为 `9c1c2e7c9d9fc0c71939e6e3c957e05c7c20000b`。
- PR #4：`agent/user-client` → `develop`，2026-07-22 09:03:34 +08:00 squash merge 为 `a93b4306087c7dc30be234b62c6aab96bf811965`。
- C 第二次 rebase：无冲突，Head 更新为 `1657a0ed3a18a8cf7d5c0b7026e68c90dda2fc28`。
- PR #5：`agent/platform-center` → `develop`，2026-07-22 09:18:04 +08:00 squash merge 为 `ba9c0c92df3b8927663246f5b36597f1a39db3cc`。
- 三线交付后的 `develop`：`ba9c0c92df3b8927663246f5b36597f1a39db3cc`。
- 2026-07-22 09:21 +08:00，三个 Agent 分支均已使用 `reset --hard` 与 `push --force-with-lease` 对齐三线交付共同基线；没有使用普通 `--force`。
- 总控状态分支：`agent/control-g1-merge-status`，基于 `ba9c0c9`，仅允许修改 `docs/control/**`。
- 总控状态提交的 squash merge 会产生新的 `develop` SHA；该自引用 SHA 不写入自身内容，以最终执行回报为准，并在合并后再次对齐三个 Agent 分支。

## 2026-07-23 本机体验修复

- 本地 `develop` 从 `a985fe2f069452e9d8d0cc8839ef0292245c83c1` 依次 squash 合入 C 包解析修复 `2f997219a61c92439a3dddb6a923c7d8e282add1` 与 OPS 启动编排修复 `ba03ec254619667a1072245198724fb9aecea426`，均无冲突。
- 本任务未推送远端；记录时 `origin/develop` 仍为共同基线 `a985fe2f069452e9d8d0cc8839ef0292245c83c1`。最终运行 Gate 受其他项目占用 5173 阻断，详见本机体验交接记录。
- 用户释放 5173 后，正式一键脚本与状态脚本均成功完成；最终本地体验结果记录在 `docs/control/ops/CONTROL-LOCAL-DEMO-FINAL_交接.md`。本任务仍未推送远端。

## 2026-07-23 局域网模式集成

- 共同基线为已推送的 `913a440a703b961ff48ceb232b088b8481567a72`；`agent/rag-lan-t04` 的已验证提交 `055aaac60cdce1ad5004832c0bb71129c6ab6c97` 无冲突 squash 为 `3f20686c48dbec4dd7d389e6eac7dcfe16eeb28f`。
- `control/ops-lan-t05` 的已验证提交 `b7cb6eec0bcd686cbdd9079a2d98c47083af03b5` 随后无冲突 squash 为 `978f884b41b8a1ea0c0f42ac5e5e319516f0cac`。
- 两项功能提交已按快进方式推送至 `origin/develop`；未 reset、未重写已验收历史，也未创建或冒充 GitHub PR。

## 2026-07-23 真实 LAN 启动验证

- 用户将物理以太网改为 `Private` 后，正式 `启动局域网客服.bat` 成功完成 A/B/C 启动、迁移、测试包幂等检查、47/47 同步和真实 Ollama chat smoke。
- 该运行验证暴露 OPS 生命周期登记缺陷：环境注入函数中的 `$name` 覆盖服务名，生成的 `.runtime` 记录名为环境变量而非服务名。此缺陷尚未修复；本节只记录事实，不产生新的业务代码提交。

## 2026-07-23 OPS LAN 运行记录修复

- 独立 Worktree `control/ops-lan-record-fix1` 从 `43db576a4fb5997d7937e2125d47af4982e5a40e` 创建。源分支先后提交 `701b537557317d3c0a8f6cd576f169b503e73fd4`（修复和回归）与 `d78ebeb`（使启动失败夹具与真实仓库 `.venv` 隔离），均已推送。
- 无冲突 squash 提交 `56acf9792bf728eaad12f8025be658a6dcfdbbcc` 已推送至 `origin/develop`。内容仅限 Windows OPS 生命周期脚本及测试；未修改 A/B/C 业务、API、模型、数据包、端口或网络策略。
- 修复提交后，对旧 LAN 进程重新取证发现 C 的历史标准记录已丢失，故未执行停止、错误记录清理或新版 LAN 重启。正式 `develop` 保持干净。
