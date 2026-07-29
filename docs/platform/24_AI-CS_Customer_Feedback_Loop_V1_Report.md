# 《AI-CS Customer Feedback Loop V1 Implementation Report》

报告日期：2026-07-29
当前阶段：Controlled Production Operation
任务卡：AI-CS Customer Feedback Loop V1 Implementation
门禁结论：`PASS_WITH_DECLARED_SECURITY_LIMITS`

## 1. 实施结论

最小可用反馈沉淀链路已经在 B/C 线实现并通过自动化验收：

```text
客服采用行为
  → C 保存 AI 行为事件
  → “未采用”即时形成 AI 问题
  → 运营人工确认问题
  → 生成知识优化任务
  → 人工补充并走既有审核流程
  → 人工重新提问并记录 AI 是否改善
```

直接采用、修改后采用、未采用都不再只停留在 B 页面。B 只有在 C 返回
`event_id`、原 `interaction_id`、`status=RECORDED` 和服务端时间后才显示保存成功。
保存失败会保留错误与幂等重试键，不会产生本地成功记录。

“未采用”事件不依赖原因表单或 A 分析完成，会立即进入 C 的 `NEW` AI 问题列表。
后续原因表单如果提交，会通过 `interaction_id` 关联同一事件并补充问题分类。

角色边界保持不变：客服只负责通过真实采用行为发现问题；AI 提供原回答并沿用既有
分析证据能力；运营负责确认问题、补充知识和记录复验。系统不替运营生成知识。

## 2. Phase 1：AI 行为事件沉淀

新增共享契约 `ai-interaction-event.v1`：

- `POST /api/v1/ai-interaction-events`
- 必须携带 `Idempotency-Key`
- 行为：`DIRECT_ACCEPT`、`EDITED_ACCEPT`、`REJECTED`
- 必要字段：`interaction_id`、店铺、商品、可选 SKU、行为类型、客服报告人
- C 生成：`event_id`、`occurred_at`、`RECORDED` 回执

B 使用 A 返回的 `request_id` 作为 `interaction_id`；如果旧 A 响应没有
`request_id`，B 生成本次页面会话内的稳定关联 ID。商品和 SKU 同时保存业务显示名与
现有目录标识，没有新建或改造 Store/Product/SKU 主数据。

事件采用请求级幂等。相同客服与相同幂等键、相同内容返回原回执；相同键绑定不同内容
返回 `409 AI_INTERACTION_EVENT_IDEMPOTENCY_CONFLICT`。

## 3. Phase 2：C AI 问题中心

新增 C Admin 路径：

- 页面：`/ai-issues`
- 列表：`GET /api/v1/admin/ai-feedback-loop/issues`
- 状态操作：`PATCH /api/v1/admin/ai-feedback-loop/issues/{problem_id}/status`

列表真实展示：

- 商品与 SKU
- 问题摘要
- AI 回答摘要
- 问题类型
- 出现次数
- `NEW / CONFIRMED / PROCESSING / SOLVED / VERIFIED`

聚合键由 C 计算：店铺、商品、SKU 和最小化问题摘要的规范化哈希。重复的未采用事件
增加出现次数，不重复制造列表行。已经 `SOLVED` 或 `VERIFIED` 的问题如果再次出现，
会重新回到 `NEW`，避免把回归问题误认为仍然闭环。

问题类型采用：

- `KNOWLEDGE_MISSING`
- `PRODUCT_INFO_ERROR`
- `SKU_ERROR`
- `INCOMPLETE_ANSWER`
- `RISK_ISSUE`
- `EXPRESSION_ISSUE`
- `UNCLASSIFIED`（待人工/分析确认）

运营必须选择受控类型才能从 `NEW` 进入 `CONFIRMED`。所有状态迁移均由显式运营操作
触发，非法跳转返回 `409`。

## 4. Phase 3：知识缺口关联与重新验证

新增 C Admin 操作：

- `POST /api/v1/admin/ai-feedback-loop/issues/{problem_id}/knowledge-tasks`
- `PATCH /api/v1/admin/ai-feedback-loop/knowledge-tasks/{task_id}/status`
- `POST /api/v1/admin/ai-feedback-loop/knowledge-tasks/{task_id}/verifications`

任务关联：

- 商品
- SKU
- 来源问题 `source_problem_id`
- 缺失主题

任务状态：

- `PENDING`：待补充
- `IN_PROGRESS`：处理中
- `COMPLETED`：已补充
- `VERIFIED`：已验证

复验必须在任务“已补充”后由运营人工记录：

- `IMPROVED`：任务与问题进入 `VERIFIED`
- `NOT_IMPROVED`：任务与问题返回处理中，继续补充后可再次复验

本流程只记录知识优化待办、人工补充状态与重新提问结果。它不生成知识正文，不调用
知识发布，不修改 Prompt，不训练模型，也不自动给客户发送消息。

## 5. 数据最小化与隐私边界

新事件和新问题不保存完整对话、客户档案、订单正文、截图或 Answer Trace，只保存
问题、AI 回答和人工最终回复的最多 240 字摘要。B 先做一次最小化，C 在持久化前再次：

- 替换常见手机号、邮箱、身份证号和长数字编号
- 合并空白
- 截断为 240 字

关联新事件的既有 AI 问题原因记录也只保存同样的最小化摘要，并标记
`redaction_version=feedback-summary-v1`。

该规则是 V1 数据最小化，不是“完整自动脱敏”声明；姓名、自然语言地址和非常规标识
仍可能需要提交人遵守页面提示并人工去标识化。当前试点报告人标识不是认证或 RBAC。

## 6. 契约与兼容

共享契约从 `0.1.0` 增量升级到 `0.2.0`：

- 新增 create/receipt 两个 JSON Schema
- 新增错误码、版本记录、兼容与回滚说明
- 旧 `feedback.schema.json`、A badcase 导出和分析回写保持不变
- 既有 `POST /api/v1/ai-response-feedback` 只增加可选 `interaction_id`

影响线：

- B：新增事件生产者；只有真实 `RECORDED` 回执才显示成功
- C：事件权威记录、问题聚合、知识任务和运营状态的所有者
- A：无代码、路径、字段或行为变更

发布顺序为 C 后 B；回滚顺序为 B 后 C。C 数据迁移只新增四张 SQLite 表，降级只删除
本任务表，不影响既有反馈、案例、知识资料或目录表。

## 7. 验收结果

| 验收项 | 验证证据 | 结论 |
| --- | --- | --- |
| 点击未采用后真实保存 | B 失败不显示成功；C API 测试查询 `AIInteractionEvent` 持久行和 `RECORDED` 回执 | PASS |
| C 看到对应商品/SKU问题 | `REJECTED` 后立即查询 `/issues`，返回测试商品、红色款、摘要、类型、次数和 `NEW` | PASS |
| 运营处理问题 | 测试执行 `NEW → CONFIRMED → PROCESSING` 和非法跳转保护 | PASS |
| 补知识后重新验证 | 测试执行任务待补充、处理中、已补充；先记录未改善回退，再补充并记录已改善 | PASS |
| 客服问题→AI问题→知识补充→AI改善 | 后端端到端专项和 Admin 页面动作测试覆盖完整状态链 | PASS |

## 8. 自动化证据

- C Backend：`94 passed`
- Customer Feedback Loop 专项：`3 passed`
- SQLite Alembic：`upgrade head → downgrade 0007 → upgrade head`，最终
  `0008_customer_feedback_loop_v1 (head)`
- C Admin：typecheck 通过；Vitest `25 files / 53 tests`；production build 通过
- B Frontend：typecheck 通过；Vitest `28 files / 115 tests`；production build 通过
- 共享契约：6 个 JSON Schema 全部通过 Draft 2020-12 schema 检查，版本 `0.2.0`
- `git diff --check`：通过

测试只使用合成、去标识化数据和隔离 SQLite；没有写入真实客户数据或生产库。

## 9. 明确未实施

- 未修改 A 核心能力
- 未进入 Master Data
- 未实现登录、RBAC 或正式敏感访问审计
- 未引入 PostgreSQL
- 未实现完整 Answer Trace
- 未自动生成知识
- 未自动发布知识到 RAG
- 未自动修改 Prompt
- 未自动训练模型
- 未自动发送客户消息、修改订单、退款或写 ERP

## 10. 文件入口

- B 事件客户端：`frontend/src/api/aiInteractionEventClient.ts`
- B 操作入口：`frontend/src/views/AiChat.vue`
- C 模型与规则：`platform_backend/app/customer_feedback_loop/`
- C 迁移：`platform_backend/migrations/versions/0008_customer_feedback_loop_v1.py`
- C 运营页面：`admin_web/src/views/AiIssueCenterView.vue`
- 共享契约：`contracts/schemas/ai-interaction-event-*.schema.json`
- 兼容说明：`contracts/compatibility/customer-feedback-loop-v1.md`
