# B 线 AI 上下文

更新时间：2026-07-25

## 当前任务

- 任务：`MVP-PLUS-02-FEEDBACK 客服反馈闭环入口`。
- 分支：`codex/customer-pilot-experience`；Draft PR [#34](https://github.com/666whatcanisay/AI-Customer-Service-for-Toys/pull/34)，标题 `feat(customer): add AI feedback capture`，目标分支 `develop`。MVP-PLUS-01 Draft PR #29 已合并。
- 状态：B 前端本地验收 `PASS`；消费已冻结 `ai-feedback.v1-draft` 的独立创建协议，尚未执行真实跨线 POST 联调。

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

## 试运行体验边界

- 首次引导只展示测试版使用流程与“AI 建议需要人工确认”，关闭状态仅保存本机布尔标记。
- `DIRECT_ANSWER/CONTROLLED_ANSWER/TRANSFER_HUMAN` 的展示依次为“🟢 可以参考 / 🟡 建议确认 / 🔴 建议人工处理”；不改变 action wire value。
- 未采用原因 `FACT_ERROR/MISSING_INFO/STYLE_ISSUE/RISK_ISSUE/OTHER` 是独立 `AIResponseFeedback.feedback_type`，不映射为 CustomerExperienceCase 的 `feedback_type`。选择“未采用”后由独立弹窗提交真实 POST；`OTHER` 需要去标识化说明。
- B 严格请求 `POST /platform-api/api/v1/ai-response-feedback`，携带受控三字段 context；只在收到顶层 `feedback_id/status=NEW/analysis_status=NEW/created_at` 后展示成功。错误、未知响应和契约偏差不产生本地成功或优秀案例回退。

## 安全与验证

- 只用于内部测试，不收集客户姓名、电话、地址、完整订单号或隐私截图；不自动发送消息或执行订单动作。
- Node：`v24.14.0`。
- `vue-tsc --noEmit`：PASS。
- Vitest：22 文件 / 87 测试 PASS，覆盖首次引导、状态展示、AI 问题反馈提交/失败、优秀案例独立边界和原 AI 客服回归。
- `vite build`：PASS；保留单 JS chunk 大于 500 kB 的已知警告。
