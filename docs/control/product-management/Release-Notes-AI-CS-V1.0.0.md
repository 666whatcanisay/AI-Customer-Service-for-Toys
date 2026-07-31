# AI-CS V1.0.0 Release Notes

发布状态：`INTERNAL_PRODUCTION_READY`

正式引用：`ai-cs-v1.0.0`

## 发布亮点

- AI-CS 正式内部生产版。
- R008 Runtime 稳定化与单一运行基线。
- R009 商品知识 Excel 导入、Merge 预览与人工审核闭环。
- R006 Customer Available Catalog 客服可用目录。
- R006.1 AI 知识增量发布、Publication Receipt 与 RAG 可见性。
- R006.2 客服目录自动刷新与运营启用体验优化。
- 本地 `Qwen3.5:9B` 模型支持，保持人工确认与禁止自动发送边界。
- RAG 商品知识检索、来源引用与商品级增量同步。
- 商品从知识审核、AI 发布、客服启用到客服使用的生命周期管理。

## 发布范围

- 收敛 R006 Customer Available Catalog、R006.1 AI Knowledge Publishing、R006.2 Customer Experience Polish 与既有 R009 商品知识导入闭环。
- 正式化 B/C 用户可见运行身份，保留人工确认与全部禁止自动业务动作的安全边界。
- 通过 `0012_internal_production_finalization_v1` 将符合历史初始化证据的 Store 当前来源标记为 `INITIAL_IMPORT`。
- 默认隐藏旧测试工具入口；Import Center 六模板保持原定位和数量。

## 兼容性

- Contracts：`0.5.0`。
- `INITIAL_IMPORT` 为加性枚举；`TEST`、`PILOT` 和旧合同仍可解析。
- C 继续拥有客服可用目录；B 只消费 C 投影。
- 不改 A 回答、Prompt、RAG 发布、R009 Merge 或 Windows 启停规则。

## 数据与迁移

- Revision：`0012_internal_production_finalization_v1`。
- 迁移仅更新 1 个具备 `IMPORTED_TEST_ONLY + 0.3.1-test` 证据的 Store，并生成来源正式化审计记录。
- Product、SKU、导入批次、商品知识、activation/publication receipt、Chunk 和 Embedding 均未删除或重建。
- 活动集合保持 `test_knowledge_v031=56`，这是内部兼容物理名，不作为用户可见环境身份。

## 验证摘要

- A：109 passed，3 skipped。
- B：120 passed，typecheck/build 通过。
- C：全量 pytest 通过，contracts 5 passed，Alembic check 通过。
- Admin：64 passed，typecheck/build 通过。
- 浏览器：Admin 四页面与六模板通过；B 选择 PUBLISHED 商品、生成回答并验证 3 条同商品引用；安全提示通过。

## 已关闭问题

- `BUG-B-003`：移除 B 侧栏残留“测试工作台 / 不是正式登录系统”文案。

## 运行

继续使用既有标准脚本：

```powershell
.\scripts\windows\start_ai_customer_service.ps1
.\scripts\windows\status_ai_customer_service.ps1
.\scripts\windows\stop_ai_customer_service.ps1
```

端口保持 B 5173、Admin 5174、A 8000、C 8011。

## 回滚

- 代码、SQLite 与 RAG 必须按同一受控批次整体回滚。
- 已保留在线/离线 0012 快照、隔离验证的 0011 快照和 RAG manifest。
- 禁止通过删除表、collection、Chunk、Embedding 或 receipt 实现回滚。

## 未包含

- R003 完整业务验收、R005 真实反馈闭环、R007 外部网络策略处理。
- ERP、外部平台自动同步、自动发送、自动退款、订单修改、RBAC/SSO 和 RAG 全量重建。
