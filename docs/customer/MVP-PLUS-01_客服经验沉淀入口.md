# MVP-PLUS-01 客服经验沉淀入口

日期：2026-07-25

Draft PR：[#29](https://github.com/666whatcanisay/AI-Customer-Service-for-Toys/pull/29)（目标分支：`develop`）。

## 交付

- AI 回答反馈区保留“直接采用 / 修改后采用 / 未采用”，并在选择反馈后提供“⭐ 保存优秀案例”。
- 表单以当前 AI 问答上下文提交 `store_code`、`product_id`、`sku_id`、`question`、`ai_answer`、`final_answer`、`feedback_type`、`created_by`。
- 新增 `/experience-cases`（我的案例）。成功记录展示 `NEW`、`REVIEWING`、`APPROVED`、`REJECTED` 的中文状态，不展示或持久化原始问答内容。
- 失败时明确显示 C 接口错误，且不生成本地成功条目。

## 接口与隐私

生产客户端只调用真实 `POST /platform-api/api/v1/customer-experience-cases`，不含 Mock 成功回退。C 未发布列表 GET 契约，因此页面只显示本次浏览器会话中已收到真实 POST 成功响应的最小摘要；刷新后不会假装存在远端历史。

提交前页面提醒排除客户姓名、电话、地址、完整订单号和隐私截图。问题、AI 回复和最终回复不会写入 localStorage 或会话摘要。

## 验证

- `vue-tsc --noEmit`：PASS
- Vitest：19 文件 / 77 测试 PASS
- `vite build`：PASS

结论：B 前端交付 `PASS`。真实 C 跨线联调 `BLOCKED`，等待 C 发布版本化 POST 响应与 GET 查询契约；未修改 `contracts/**` 或 C 代码。
