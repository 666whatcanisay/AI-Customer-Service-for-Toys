# AI-CS Product Stable V1 Candidate Release Notes

状态：`CANDIDATE / R006_IMPLEMENTED / PRODUCTION_RELEASE_PENDING`

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
- R006已在Feature候选实现并通过隔离浏览器验收，但尚未部署正式Runtime或迁移正式数据库。

## 发布阻塞

`BUG-B-001` 已在R006候选中修复并验证；正式`AI-CS@42bafcf/0008`仍使用旧实现，须经独立发布Gate后才能标记Production Verified。
