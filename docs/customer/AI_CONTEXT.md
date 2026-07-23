# B 线 AI 上下文

更新时间：2026-07-23

## 当前任务

- 任务卡：B-T04 客服工作台小白化改造。
- 分支：`agent/user-client-t04`。
- 基线：`origin/develop@0c447ae03da445b2b92a5559dc916d2616825ce3`。
- 状态：三步页面与自动化验证完成，等待提交和 Draft PR。

## 允许范围

- `frontend/**`
- `docs/customer/**`

禁止修改 `backend/**`、`platform_backend/**`、`admin_web/**`、
`scripts/windows/**`、`contracts/**`。

## 当前页面

入口：`frontend/src/views/AiChat.vue`。

面向客服的流程：

1. 选择平台/店铺、商品和可选 SKU。
2. 粘贴或输入客户问题并生成建议。
3. 编辑建议回复、复制当前文本，并记录采用结果。

店铺选择保存在浏览器本地；切换店铺会清空商品和 SKU，
切换商品会清空 SKU。来源和技术字段默认隐藏。

## 冻结接口

RAG 服务由 `VITE_RAG_API_BASE_URL` 配置，开发默认 `http://127.0.0.1:8000`：

- `GET /api/health`
- `POST /api/chat`

目录服务由 `VITE_PLATFORM_API_BASE_URL` 配置，当前开发默认 `http://127.0.0.1:8011`：

- `GET /health`
- `GET /api/v1/test-catalog/stores`
- `GET /api/v1/test-catalog/products?store_code=`
- `GET /api/v1/test-catalog/products/{product_id}/skus`

请求/响应差异只允许在 `frontend/src/api/*Adapter.ts` 中处理。
生产模式不得回退 Mock。本任务不修改共享 contracts。

## 安全边界

- 当前仅使用测试数据，禁止直接用于真实客户。
- 页面只生成建议，不自动发送到电商平台。
- 不实现浏览器扩展、登录、快麦或 B-T05。
- 反馈 API 未发布，采用结果只记录在当前页面。

## 验证

Node：`v24.14.0`。

项目脚本：

- `npm run typecheck`
- `npm run test`
- `npm run build`

2026-07-23 结果：typecheck PASS；Vitest 4 文件、30/30 PASS；
production build PASS。构建仍报告 JavaScript chunk 超过 500 kB。

## 交接

- A/C 真实服务可用后再做页面 smoke，不得用 Mock 冒充联调成功。
- 下一任务不得自动进入 B-T05。
