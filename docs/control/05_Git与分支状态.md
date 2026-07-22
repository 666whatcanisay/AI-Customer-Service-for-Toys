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
