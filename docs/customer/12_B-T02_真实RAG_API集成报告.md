# B-T02 真实 RAG API 集成报告

日期：2026-07-22

## 交付范围

B 线客服工作台已实现以下链路：

```text
输入客户问题
→ POST /api/chat
→ adapter 统一字段差异
→ 展示建议回复、动作、风险和引用
→ 客服编辑或复制
→ 在当前页面记录直接采用、修改后采用或未采用
```

实现仅修改 `frontend/**` 与 `docs/customer/**`。未修改 `contracts/**`、`backend/**`、`platform_backend/**` 或 `admin_web/**`；未开发浏览器扩展，也未启动 B-T03。

## API 集成

- 环境变量：`VITE_RAG_API_BASE_URL`，开发默认值为 `http://127.0.0.1:8000`。
- 健康检查：`GET /api/health`。
- 聊天：`POST /api/chat`，当前请求为 `{ "message": string }`。
- 生产代码没有 Mock 回退；Mock 只存在于 Vitest 组件测试。
- 超时固定为 15 秒；网络错误、HTTP 422、HTTP 500/503、共享错误码和取消请求通过统一错误映射处理。

总控同步的 A 线目标顶层字段为 `answer`、`action`、`sources`、`model`、`latency_ms`、`request_id`；source 目标字段为 `source_name`、`page`、`chunk_id`、`distance`、`excerpt`。兼容 adapter 同时接受当前运行实例的 `file`、`content_preview` 与 `elapsed_ms` 等遗留字段。A 的 `ANSWER` 动作集中映射为客户端的 `DIRECT_ANSWER`；缺失 risk 保持 `null`，不得猜测。

共享 contracts v0.1.0 未变化。当前 A `/api/chat` 请求仍不是共享 `assistant-request` 的完整对象，这一兼容行为仅在 B 线 adapter 与文档中记录。

## 页面能力

- 客户问题输入、Enter 提交和重复提交保护。
- 请求 Loading 和主动取消。
- 建议回复编辑、动作/风险标签、警告与待补字段。
- 来源文件、页码、片段 ID、摘要和知识版本（API 提供时）。
- 一键复制；页面明确提示由客服人工发送。
- 直接采用、修改后采用、未采用三种状态。
- API 不可用、超时、取消和契约响应异常提示。

A 线尚未发布反馈端点。采用结果只在当前页面明确记录，页面直接展示“反馈 API 待发布”，不会用假数据冒充远端提交成功。

## 验证证据

- `npm run typecheck`：PASS，退出码 0。
- `npm run test`：PASS，2 个测试文件、7 个测试全部通过。
- `npm run build`：PASS，Vite 5.4.21 production build 完成。
- 真实 health smoke：`http://127.0.0.1:8000/api/health` 可达，`ready=true`。
- 真实 chat smoke：使用合成问题请求 `/api/chat`，返回非空回答与 2 条来源。

运行中的 A 实例仍返回 `file/page/distance/content_preview`，未返回 action、risk、model、latency_ms、request_id；这与总控同步的正在定稿字段存在版本差异，但页面通过 adapter 正确降级为“动作未分类/风险未分类”，真实回答与引用链路可用。

## 已知风险与回滚

- A 线响应仍在收敛，B 线需要保留 adapter 回归测试。
- 反馈端点未发布，采用记录不会跨页面持久化。
- 构建仍有大 chunk 与 Vite CJS API 警告，未在本任务扩展范围处理。
- `npm install` 报告 7 个依赖漏洞（5 moderate、1 high、1 critical）；本轮未自动升级或执行破坏性修复。

回滚时可撤销 B-T02 提交；没有数据库迁移、契约变更或后端状态需要回滚。
