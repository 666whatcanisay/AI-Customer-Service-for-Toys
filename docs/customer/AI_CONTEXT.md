# B 线 AI 上下文

更新时间：2026-07-23

## 当前任务

- 任务：MVP-BATCH-05 统一局域网入口与网络自诊断。
- 分支：`codex/mvp-lan-batch-05`，从最新 `origin/develop` 隔离创建。
- 状态：实现和隔离验证已完成，等待 Draft PR 评审；正式主仓库运行服务未被本任务修改。

## 允许范围

- `frontend/**`
- `scripts/windows/**`
- `docs/control/**`
- `docs/customer/**`

禁止修改 `backend/**`、`platform_backend/**`、`admin_web/**`、`contracts/**`。

## 当前页面

入口：`frontend/src/views/AiChat.vue`。

面向客服的流程：

1. 选择平台/店铺、商品和可选 SKU。
2. 粘贴或输入客户问题并生成建议。
3. 编辑建议回复、复制当前文本，并记录采用结果。

店铺选择保存在浏览器本地；切换店铺会清空商品和 SKU，
切换商品会清空 SKU。来源和技术字段默认隐藏。

## 冻结接口

RAG 服务由 `VITE_RAG_API_BASE_URL` 配置，默认使用同源代理基址 `/rag-api`；显式设置完整 URL 时保留直连排错模式：

- `GET /api/health`
- `POST /api/chat`

目录服务由 `VITE_PLATFORM_API_BASE_URL` 配置，默认使用同源代理基址 `/platform-api`；显式设置完整 URL 时保留直连排错模式：

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

2026-07-24 结果：`vue-tsc --noEmit` PASS；Vitest 5 文件、33/33 PASS；
production build PASS。1366×768 保持双栏；低高度时允许页面或面板滚动，不再仅因高度切换为单栏。构建仍报告 JavaScript chunk 超过 500 kB。

## 交接

- 本机 A/C 已完成真实页面 smoke；后续环境仍必须独立验证，不得用 Mock 冒充联调成功。
- 下一任务不得自动进入 B-T05。

## MVP-BATCH-05 前端路由

- 客服浏览器只访问 `http://服务器IPv4:5173/`。Vite 只允许两个固定代理：`/rag-api/**` 到 `127.0.0.1:8000`，`/platform-api/**` 到 `127.0.0.1:8011`；不存在任意转发代理。
- API 请求路径、Adapter、错误映射和共享 contracts 没有改变；生产模式不会回退 Mock。
- 技术详情默认折叠，显示前端版本、Git 短 SHA、启动模式、API 模式和当前客服入口，不干扰客服选择商品、生成建议、编辑与复制的流程。
- 临时 Vite 冒烟已实际验证：通过 5173 的等价代理端口请求 `/rag-api/api/health` 与 `/platform-api/health` 均返回 HTTP 200。正式局域网监听边界仍需在 PR 审核并部署后完成真实验收。
