# Admin UI Hotfix Release V1

日期：2026-07-28
代码基线：`origin/develop@07eb96239e4cc5aa680e2b739b4a3d09dd6a81cf`

## 范围

本次仅发布两个已验证的运营后台界面修复：

| 发布顺序 | 候选提交 | 原始 Hotfix | 修复内容 |
| --- | --- | --- | --- |
| 1 | `7787606` | `8c8a9a8` | 资料来源表的长文件名和 SHA-256 在列内换行，表格容器不再撑宽页面。 |
| 2 | `84366f7` | `80097cf` | 运营概览卡片的数值与“份/条”同行，业务说明独立展示。 |

未修改 `contracts/**`、数据库、迁移、平台或 RAG API、模型/Prompt、业务动作、网络策略和启动脚本。

## 验证

- `git diff --check`：通过。
- Admin `pnpm typecheck`：通过。
- Admin Vitest：`42 passed`。
- Admin production build：通过。
- 两个问题均已用真实 5174 代理数据做浏览器预览：来源页无页面级横向溢出；运营概览的数值与单位保持同一行。

## 运行切换约束

正式运行切换不依赖端口可达性判断。必须先用受管停止流程核验并停止当前 `07eb962` 的 A/C/B/Admin，再使用正式脚本从合入后的同一 SHA 启动 C → A → B → Admin，并复核 5173、5174、health、运行记录和浏览器入口。

任务指定的 `.agent/bootstrap.md`、`docs/control/project-state/project-state.yaml` 和 `docs/control/release-checklist.md` 当前不存在；本记录不伪造它们，改以实际 Git、测试和运行 Gate 证据为准。
