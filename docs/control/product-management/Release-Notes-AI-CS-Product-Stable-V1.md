# AI-CS Product Stable V1 Candidate Release Notes

状态：`CANDIDATE / BLOCKED_BY_R006`

## 已完成

- R008 单目录 Runtime 基线复验，完成三轮启停和 A/C 故障恢复。
- 修复本地 Ollama 请求被代理劫持导致的 502。
- 修复不存在商品跨商品检索回退。
- 修复年龄意图误路由和结构化字段缺证据时生成内容。
- R009 在隔离 0009 环境完成真实 Excel 浏览器回归。
- 建立 `tests/e2e/customer`、`admin`、`workflows` 可复用 Playwright 资产。

## 未发布内容

- R009 仍未迁移正式数据库；正式 Runtime 保持 0008。
- R009 导入结果未自动发布 RAG，未验证 B 立即消费。
- R006 未实施。

## 发布阻塞

`BUG-B-001` 使 B 无法选择商品并完成每日咨询。解决必须进入经授权的 R006 C 最终业务投影实现，不能在本版本临时过滤。
