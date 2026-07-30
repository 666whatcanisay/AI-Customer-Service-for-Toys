# AI-CS R009 Product Knowledge Import Integration Acceptance Report V2

## 1. 部署版本与隔离边界

- 分支：`feature/r009-product-knowledge-import-v1`
- 基线：`dd379278837a4f816dfb626292a26b0c54cce0cc`
- 原实现提交：`871b6290301f8587488bb8b282d4f60034fb37ba`
- 真实模板兼容与集成修复提交：`817198a`
- 验收 C API：`http://127.0.0.1:19011`
- 验收 Admin：`http://127.0.0.1:15179/knowledge-materials`
- 验收数据库：Feature Worktree 下 `.runtime/r009-integration-acceptance/platform-v2.sqlite3`，受 Git 忽略。

正式 Pilot 继续运行 `AI-CS@dd379278` 的 5173/5174/8000/8011；正式 Platform SQLite 保持 `0008_customer_feedback_loop_v1`，没有 R009 表。本次没有停止、迁移或修改正式 Pilot。

## 2. Integration Fix

`ProductKnowledgeTemplateParser` 不再固定第4行。它在数据填写和示例数据工作表前100行中扫描完整且唯一的16字段冻结表头，并在字段说明中扫描同一16字段纵向清单；找不到或找到多个候选都会阻断，不执行动态字段推断，也不调用 LLM。

来源日期和是否人工确认从行级必填项移除。来源日期为空时使用批次系统导入日期，并记录 `source_date_origin=SYSTEM_IMPORT_DATE`；是否人工确认为空时保留 `null` 审计证据。Excel 的人工确认值不再决定正式审核状态，只有 C 系统的显式 `APPROVE` 才将商品标记为 `APPROVED`。

真实 Runtime 验收发现 Session 配置为 `autoflush=false` 时，最后一个变更集审核后批次可能停在 `PARTIALLY_REVIEWED`。修复在汇总待审核数量前显式 flush，并将测试 Session 调整为与 Runtime 相同的行为。

## 3. Migration与Runtime验证

- 隔离 SQLite：`0008 → 0009 → 0008 → 0009` 往返通过。
- `alembic check`：`No new upgrade operations detected`。
- 最终验收库 revision：`0009_product_knowledge_import_v1`。
- OpenAPI：4条 `/api/v1/admin/product-knowledge-imports` 路由可用。
- Admin：15179返回HTTP 200，运行中的页面包含“选择店铺、选择模板、上传并审核”、未开放模板提示和字段级Merge列。
- Admin回归：25个文件、55项Vitest通过；typecheck和production build通过。
- C Backend：101项pytest通过，其中R009专项6项通过。

## 4. 真实Excel解析结果

- 文件：桌面 `商品知识采集模板V1(1)(1).xlsx`
- SHA256：`c569bf7d1269f2b3a8e08b92387e178ddbe741ac290c6b42d2a73db358b13dfd`
- 店铺：`玩趣乐园积木店`，与隔离库所选店铺一致。
- 四个工作表：填写说明、数据填写、示例数据、字段说明，均存在、可见且验证通过。
- 自动识别：数据填写表头第5行；示例数据表头第5行；字段说明清单从第5行开始。
- 业务数据：19条；有效19条；无效0条；阻塞问题0条。
- 空来源日期：使用验收批次系统导入日期 `2026-07-30`。
- 空人工确认：保留为 `null`，不替代系统审核。

## 5. Merge与审核结果

为同时覆盖四类Merge，隔离验收库预置了一个同名既有商品：旧简介与Excel不同、旧包装存在而Excel为空、商品名称和材质与Excel相同。该验收夹具只存在于隔离库。

- 商品识别：18个新增、1个既有、0个冲突。
- 操作：`CREATE=18`，`UPDATE=1`。
- 字段变化：`ADD=202`，`UPDATE=1`，`KEEP=4`，`NO_CHANGE=2`。
- 审核前：目标店铺正式商品仍为1条，证明上传和预检没有直接写入正式商品。
- 人工审核收据：19张，全部为 `APPLIED`。
- 应用字段：203项。
- 审核后：目标店铺正式商品为19条；批次状态 `COMPLETED`；19个变更集均为 `APPROVED_APPLIED`。
- 既有商品简介已更新，Excel空白的包装字段保留旧值。
- 商品 `review_status=APPROVED`，`publishable=false`。
- 最终验收批次：`83b00ccb-8cd5-40a4-994c-01c815f9400a`。

## 6. 遗留问题与后续边界

- 当前浏览器控制通道没有可用浏览器，因此本次通过真实运行Admin资源、Admin组件测试和真实HTTP/API闭环完成集成验收；15179环境保留给运营进行最终可视化点击复核。
- 验收环境没有正式登录、RBAC、自动脱敏或生产安全认证；真实资料上传前仍需人工去标识化。
- R009不会自动发布RAG、激活客服、修改Prompt或触发任何业务动作。
- RAG同步和B客服消费不属于本报告范围，应另立后续任务。
- 正式Pilot仍未部署R009；正式发布必须另行执行备份、0009迁移、5174/8011受控切换和回滚Gate。

最终状态：`PRODUCT_KNOWLEDGE_IMPORT_ACCEPTANCE_READY`
