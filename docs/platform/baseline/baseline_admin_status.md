# Admin web 基线状态

## 已实现

- Vue 3 + TypeScript + Vite 单页应用。
- Vue Router：根路径重定向到 `/system-status`。
- Axios API Client：默认访问 `/api/platform/health`，超时 5 秒。
- Vite 开发代理：去掉 `/api/platform` 前缀后转发到 `127.0.0.1:8000`。
- 系统状态页：真实呈现加载、正常、断网、服务错误四种状态。
- 正常状态只显示健康接口返回的服务名、版本和 request_id，不展示虚假统计。
- Vitest 覆盖正常、断网和服务错误显示；加载状态在正常测试中验证。

## 已验证依赖

- Node.js 22.23.1（测试运行时）
- pnpm 11.9.0
- Vue 3.5.40
- Vue Router 4.6.4
- Axios 1.18.1
- Vite 6.4.3
- TypeScript 5.7.3
- Vitest 3.2.7

## 明确未实现

没有商品、SKU、知识治理、审核、风险规则、评测、登录或 Dashboard 页面；没有 Pinia 或其他全局状态层，因为单一健康页不需要它们。
