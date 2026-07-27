# MVP-PLUS-02-FEEDBACK 客服反馈闭环入口

日期：2026-07-25

Draft PR：[#34](https://github.com/666whatcanisay/AI-Customer-Service-for-Toys/pull/34)，标题为 `feat(customer): add AI feedback capture`，目标分支为 `develop`。

## 页面

- AI 回答的既有商品选择、SKU 选择、来源展示、编辑与人工复制流程未改变。
- 选择“未采用”后出现“⚑ AI 问题反馈”入口，打开标题为“为什么未采用？”的独立反馈弹窗。
- 可选择事实错误、缺少信息、表达问题、风险问题或其他；选择“其他”必须填写去标识化说明。最终人工回复可选，未发送时保持为空。
- “⭐ 收藏为优秀案例”保留给已采用/修改后采用的优秀回复；未采用不会作为经验案例提交。

## API 调用

生产客户端仅调用 `POST /platform-api/api/v1/ai-response-feedback`，并按 `ai-feedback.v1-draft` 发送受控上下文、五值 `feedback_type` 与非空 `Idempotency-Key`。新反馈会话首次提交生成唯一键，失败重试复用该键。成功只接受顶层 `feedback_id`、`status=NEW`，然后显示“反馈已记录。”；接口失败和异常回执均显示失败，不生成本地成功，也不会回退为 CustomerExperienceCase。

## 验证

- `vue-tsc --noEmit`：PASS
- Vitest：22 文件 / 87 测试 PASS
- `vite build`：PASS

结论：B 前端交付 `PASS`，Draft PR #34 已创建。构建保留单个 JavaScript chunk 超过 500 kB 的既有警告；真实 C POST 联调不在本任务内执行。
