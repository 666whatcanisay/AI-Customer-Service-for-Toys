# AI-CS C Admin UI Optimization Release V1 任务卡

## 任务

AI-CS C Admin UI Optimization Release V1

## 目标

从正式基线 `8fe36b109d533131e11609841f2ce5ec1b2d6f00` 生成仅包含 C Admin 展示优化的 Release Candidate，并在隔离 Admin 中验证导航、运营工作台、商品知识中心、导入中心和 AI 状态。

## 分支与来源

- Release 分支：`release/c-admin-ui-optimization-v1`
- 正式基线：`8fe36b109d533131e11609841f2ce5ec1b2d6f00`
- Navigation：`codex/c-admin-navigation-simplification-v1@bdacd461eb685854ec9fcf0b015ef15a3aa17346`
- Operational Workspace：`codex/c-admin-operational-workspace-optimization-v1@f50ab0ac4f11b3170a8f615a1b466a6dcb3d5400`
- UX Polish：`codex/c-admin-ux-polish-v1@1cc032bd22c999cc4ef32866121509149e265bc9`

三个优化分支为线性祖先关系：正式基线 → Navigation → Operational Workspace → UX Polish。

## 范围

- 只允许 `admin_web/**`。
- 按 Navigation → Operational Workspace → UX Polish 顺序形成 Release Candidate。
- 运行 Admin 自动测试、类型检查、生产构建和隔离浏览器验收。
- 记录正式 5173/5174/8000/8011 的前后状态，不停止或切换标准 Runtime。

## 不包含

- API、数据库、migration、contracts、R006、R009、A/RAG、Prompt、B 或 Runtime 配置修改。
- 标准 5174 部署、正式服务重启或数据库写入。
- Navigation 分支内不属于 `admin_web/**` 的历史治理文档。

## 合并边界

Navigation 分支相对正式基线包含早期 `docs/control/**` 与 `docs/platform/**` 变更。为满足本任务“只允许 `admin_web/**`”的强制范围，Release 合并保留 Navigation 分支父节点与完整 Admin 变更，但明确排除所有非 `admin_web/**` 文件。后续两个分支本身只增加 `admin_web/**` 变更。

## 成功标准

1. Release Candidate 相对正式基线的全部差异均位于 `admin_web/**`。
2. 三个来源提交均可追溯，且按指定顺序进入 Release 历史。
3. `pnpm test`、`pnpm typecheck`、`pnpm build` 全部通过。
4. 隔离浏览器验证简洁导航 6 入口、高级完整入口、运营工作台四区域、商品状态与下一步、六模板、AI 业务状态和控制台 0 error。
5. R006、R009、5173、8000、8011 未被修改或重启。

## 风险与缓解

- Navigation 携带范围外文档：合并提交中恢复为正式基线内容，并用最终 diff 范围检查阻断越界。
- 端口可达但来源错误：隔离 Admin 使用非标准端口并记录目标 Worktree、分支、SHA 与启动命令。
- 浏览器操作误写业务数据：只读访问页面、切换导航模式和展开状态，不执行启用、发布、审核或上传。
- 正式 Runtime 已存在部分服务未运行：记录为发布前既有状态，不在本任务中启动、停止或修复。

## 验收 Gate

通过代码历史、路径范围、自动测试、隔离浏览器和正式端口前后对比决定 `C_ADMIN_UI_OPTIMIZATION_RELEASE_READY`。
