# AI-CS C Admin Operational Workspace Optimization V1 任务卡

## 任务

AI-CS C Admin Operational Workspace Optimization V1

## 目标

在不增加接口、状态、权限或业务流程的前提下，将 C Admin 的运营工作台、商品知识中心、导入中心和 AI状态页面调整为业务信息优先、下一步动作清晰、技术信息默认折叠的运营体验。

## 基线与分支

- 基线：`bdacd461eb685854ec9fcf0b015ef15a3aa17346`（包含 C Admin Navigation Simplification V1）
- 分支：`codex/c-admin-operational-workspace-optimization-v1`
- 允许路径：`admin_web/**`
- 目标 Gate：`C_ADMIN_OPERATIONAL_WORKSPACE_OPTIMIZED_V1`

## 范围

- 审计并优化 `OperationsOverviewView.vue`、`KnowledgeCenterView.vue`、`ImportCenterView.vue`、`AiCapabilityCenterView.vue` 及其 Admin 测试和展示组件。
- 仅使用已有 API 已提供的数据，不新增字段或跨线依赖。
- 首页回答当前待处理、商品生命周期和 AI 是否正常三个问题。
- 商品卡片默认展示资料、客服、AI 三类业务状态和下一步动作；技术证据保留在高级展开。
- Import Center 保持六模板下载中心定位，增加四步新用户引导。
- AI状态默认展示业务结论，模型、collection、runtime、版本等信息继续折叠。

## 不包含

- API、数据库、migration、contracts、R006、R009、A/RAG、Prompt、Runtime 或 B 修改。
- 新业务模块、新统计口径、新权限、自动发布、自动客服启用或任何自动业务动作。
- 用 `0` 或空数组伪装接口失败，或使用无法由现有接口证明的“今日”指标。

## 成功标准

1. 首页以真实现有数据展示当前工作、商品生命周期、快捷操作和 AI状态。
2. 商品知识中心为每个商品给出业务可读状态和明确下一步，不默认暴露 chunk、embedding、fingerprint 或 receipt。
3. Import Center 六模板、下载能力与 R009 上传审核入口不变，并显示四步使用引导。
4. AI状态主界面显示业务状态和真实错误；技术信息默认折叠。
5. 简洁/高级导航、所有原路由和既有业务操作保持兼容。
6. `pnpm test`、`pnpm typecheck`、`pnpm build` 和隔离浏览器核心页面回归通过。

## 风险与缓解

- 缺少聚合接口：只组合页面已使用的现有接口数据，不虚构统计。
- 服务失败被显示为零：失败单独显示“暂无法读取/需要关注”，不参与数量汇总。
- 展示优化破坏写流程：保留原操作组件、确认步骤和路由，仅重排信息层级。
- 技术证据丢失：保留在显式高级展开，不从页面或接口删除。
- 正式 Runtime 受影响：在独立 Worktree 和非标准端口验收，不重启正式服务。

## 验收

以代码差异、Admin 自动测试、类型检查、生产构建、隔离浏览器 C-UI-001 至 C-UI-005 及严格路径范围共同决定 Gate。

- Admin 自动测试：`28` 个测试文件、`65` 个测试全部通过。
- 类型检查：`pnpm typecheck` 通过。
- 生产构建：`pnpm build` 通过。
- 浏览器验收：隔离端口 `15176` 上 C-UI-001 至 C-UI-005 全部通过，控制台无错误。
- 路径范围：所有变更均位于 `admin_web/**`。
- Runtime：正式端口和服务未重启、未切换。

Gate：`C_ADMIN_OPERATIONAL_WORKSPACE_OPTIMIZED_V1`
