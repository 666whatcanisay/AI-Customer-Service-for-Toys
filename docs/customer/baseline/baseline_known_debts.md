# 前端基线已知技术债

以下项目来自 B-T01 审查和 B-G1-FIX1 的真实构建证据，未通过修改业务代码掩盖：

1. `package.json` 没有 `test` 脚本，仓库中没有前端自动化测试文件；当前只有 typecheck 和 build 证据。
2. `npm ci` 报告 5 个依赖漏洞（4 moderate、1 high）。本轮未执行自动修复或大规模升级；后续应先运行可审查的 `npm audit` 并单独评估兼容性。
3. 生产构建的主 JavaScript chunk 约 1,089.81 kB（gzip 362.37 kB），超过 Vite 500 kB 警告阈值；后续可在独立任务中评估路由懒加载和 manualChunks。
4. 构建显示 Vite CJS Node API 弃用警告，以及第三方依赖 PURE 注释位置警告；当前不阻塞构建。
5. 旧页面请求 `{ message }` 并消费 `{ answer, sources }`，与共享契约 v0.1.0 要求的请求/响应字段不兼容。
6. API 调用、错误映射和页面状态仍集中在 `AiChat.vue`；没有 Pinia、独立客户端分层、复制、反馈、风险/转人工或完整引用展示。
7. 本轮没有运行浏览器 E2E、后端联调或真实客服场景；生产构建通过不等于业务闭环通过。

这些技术债不在 B-G1-FIX1 中修复。B-T02 仍须单独授权。
