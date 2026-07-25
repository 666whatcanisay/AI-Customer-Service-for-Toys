# B 线 AI 上下文

更新时间：2026-07-25

## 当前任务

- 任务：`MVP-PLUS-01 客服经验沉淀入口`。
- 分支：`codex/customer-experience-case-capture`，基线 `origin/develop@271c155`，Draft PR #29 指向 `develop`。
- 状态：`CONTRACT-FIX1` 已将 B adapter 对齐任务内冻结；等待 C 审核、A 真实评测和回写的集成闭环。

## 范围与入口

- 允许：`frontend/**`、`docs/customer/**`。
- 禁止：`backend/**`、`platform_backend/**`、`admin_web/**`、`contracts/**`、`extension/**`。
- 入口：`/`、`/ai-chat`、`/suggestions`、`/suggestions/mine`、`/experience-cases`、`/modules/:moduleKey`。

## 优秀案例边界

- 在 `/ai-chat` 的 AI 回答反馈区，三种既有反馈（直接采用、修改后采用、未采用）保持不变；保存经验案例时必须显式选择 `ADOPTED/EDITED_ADOPTED/CORRECTION/ESCALATED` 之一，页面反馈不得直接发送或静默映射。
- 生产客户端唯一访问 `POST /platform-api/api/v1/customer-experience-cases`；不使用 Mock 回退。
- 请求严格为 `store_code/product_id/sku_id/question/ai_answer/final_answer/feedback_type/created_by`。
- 成功只消费顶层 `case_id/review_status`，其中 `review_status` 仅限 `NEW/REVIEWING/APPROVED/REJECTED`；不兼容 `status` 或 `data` 包装。未知或失败响应必须显示错误，且不得生成本地成功。
- C 未发布 GET 契约；`/experience-cases` 仅展示当前会话已真实成功的最小摘要，不存 raw 问题、AI 回复或最终回复，刷新后明确提示等待 C 查询接口。

## 安全与验证

- 只用于内部测试，不收集客户姓名、电话、地址、完整订单号或隐私截图；不自动发送消息或执行订单动作。
- Node：`v24.14.0`。
- `vue-tsc --noEmit`：PASS。
- Vitest：19 文件 / 77 测试 PASS，覆盖保存、失败提示、状态展示和原 AI 客服回归。
- `vite build`：PASS；保留单 JS chunk 大于 500 kB 的已知警告。
