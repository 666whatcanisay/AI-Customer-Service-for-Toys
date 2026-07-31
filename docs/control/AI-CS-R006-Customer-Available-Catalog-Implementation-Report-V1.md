# AI-CS R006 Customer Available Catalog Implementation Report V1

> 日期：2026-07-31
>
> 分支：`feature/r006-customer-available-catalog-v1`
>
> 实现基线：`stabilization/product-stable-v1@1fccb41`
>
> 代码与测试候选：`8cbd92b`
>
> 正式 Runtime 保护锚点：`AI-CS@42bafcf`、数据库 `0008_customer_feedback_loop_v1`

## 1. 交付结论

R006 Customer Available Catalog 已在受控 Feature 分支完成实现并通过隔离数据库、全量自动测试和跨端浏览器验收。C 现在是 `data_source`、`customer_service_status`、activation receipt 和客服可用目录投影的唯一 Owner；B 只消费 C 的最终投影，不再根据旧测试字段判断数据可信度。

本任务没有迁移正式数据库、切换正式 Runtime 或修改正式业务数据。正式发布需要独立 Release Gate，因此本报告的结论是“实现完成、候选验证通过、Production Release 待授权”。

## 2. 交付提交

| 顺序 | Commit | 内容 |
| --- | --- | --- |
| 1 | `673dca6` | contracts `0.3.0` 与 Customer Service Catalog 契约 |
| 2 | `68457e1` | C Provider、`0010` migration、状态/receipt/投影 |
| 3 | `e858c02` | C Admin 店铺/商品启停与 receipt 查看入口 |
| 4 | `04e4a84` | B Consumer 切换到 C 最终目录投影 |
| 5 | `8cbd92b` | R006 隔离浏览器跨端验收用例 |

所有提交均按模块选择性暂存，没有使用 `git add .`。

## 3. Contracts 0.3.0

共享契约从 `0.2.0` 以 additive 方式升级为 `0.3.0`，保留原有 schema，不删除或重写 0.2.0 能力。新增：

- `customer-service-catalog.v1.schema.json`；
- activation request、response、receipt 三个 schema；
- changelog、错误码、兼容性说明和 A/B/C 受影响线路复核；
- 客服目录 envelope 固定为 `pilot-business-catalog.v1.1`，只允许 `TEST/PILOT` 与最终 `ENABLED` items；
- `allow_auto_send=false` 继续作为硬安全边界，不因客服可用状态而改变。

## 4. Migration 0010

新增 `0010_customer_available_catalog_v1`，其 `down_revision` 为 `0009_product_knowledge_import_v1`；既有 `0009` 文件未修改。

迁移内容：

- Store 增加 `data_source`、`customer_service_status`、状态更新时间和操作人；
- Product 增加 `customer_service_status`、状态更新时间和操作人；
- 新增 `catalog_activation_receipts`、`catalog_activation_idempotency`、`catalog_activation_initializations`；
- SKU 不增加独立客服状态，运行时继承 Product；
- `IMPORTED_TEST_ONLY + 0.3.1-test` 初始化为 `TEST + ENABLED`；
- `MANUAL_CREATED + c-operation-store.v1` 初始化为 `PILOT + DISABLED`；
- 未知或冲突来源保持隔离，不进入客服投影；
- 每个被识别的 Store/Product 生成可审计初始化 receipt，并记录初始化 manifest。

隔离 SQLite 已执行 `0009 → 0010 → 0009 → 0010` 往返测试，正式数据库没有执行 `0010`。

## 5. C Customer Available Catalog Provider

C 提供最终只读投影：

- `GET /api/v1/customer-service/catalog/stores`；
- `GET /api/v1/customer-service/catalog/products?store_code=...`；
- `GET /api/v1/customer-service/catalog/products/{product_id}/skus`。

投影规则：

- 只有最终 `ENABLED` 的 Store/Product 才进入 B；
- Store 为 `DISABLED` 时阻断下游 Product/SKU，但不改写 Product 保存状态；
- SKU 继承 Product，并逐条验证父子关系；
- 单条未知来源、缺字段或关系异常只形成 `PARTIAL` warning 并隔离该条，不能清空其他可用目录；
- `publishable`、`production_usable`、`test_data_mode`、销售状态和知识状态均不承担客服准入裁决。

C Admin 状态接口：

- `PUT /api/v1/admin/operations/stores/{store_ref}/customer-service-status`；
- `PUT /api/v1/admin/operations/products/{product_id}/customer-service-status`；
- `GET /api/v1/admin/operations/activation-receipts/{receipt_id}`；
- `GET /api/v1/admin/operations/activation-receipts?entity_type=...&entity_ref=...`。

状态变更要求人工操作人、确认说明和 `Idempotency-Key`。同键重试返回同一结果；同状态请求返回 `changed=false`，不生成重复变化 receipt。

## 6. C Admin 控制入口

现有设计语言和导航未重做，只在现有店铺管理、商品知识列表和商品详情增加最小控制能力：

- 查看 `TEST/PILOT` 来源、客服状态、最后修改时间和操作人；
- 店铺和商品启用/停用；
- 查看 activation receipt 历史；
- 操作人为空时禁止提交；
- Store 停用明确提示只阻断投影，不级联覆盖 Product 状态。

Import Center、R009 导入页面及六类模板定位均未修改。

## 7. B Consumer 切换

B 的三个目录调用已切换为 `/api/v1/customer-service/catalog/**`，并只消费 C 返回的最终 items。已删除目录准入链路对以下旧字段的依赖：

- `trial_enabled`；
- `test_data_mode`；
- `production_usable`；
- `publishable`。

B 不包含业务白名单、默认店铺、本地启用或旧字段兼容矩阵。单条结构异常由 adapter 隔离；若整个响应 envelope 无效，B 显示既有友好错误，而不是自行猜测业务可用性。客服页面布局、问答流程以及传给 A 的 tenant/store/product/SKU 上下文保持不变。

## 8. 测试结果

| 范围 | 结果 |
| --- | --- |
| Contracts | `4 passed` |
| C Platform Backend | `110 passed`；含 `0010` 往返、状态幂等、receipt、异常隔离、Store阻断和SKU继承 |
| B Frontend | `28 files / 117 passed`；typecheck、build PASS |
| C Admin | `26 files / 58 passed`；typecheck、build PASS |
| Browser E2E | PASS；隔离端口 `15183/15184/19021`、隔离 SQLite；结束后全部关闭 |
| 边界检查 | A、RAG、Prompt、R009、Import Center、`0009` 无 diff |

浏览器证据覆盖：

1. 一条未知 Store、一条坏 Product 和一条坏 SKU 被分别隔离，TEST 可用目录仍正常显示；
2. `TEST + ENABLED` 在 B 可见；
3. `PILOT + DISABLED` 初始不可见；
4. C Admin 启用 Store 和 Product 后，B 可见对应店铺和商品；
5. C Admin 停用 Store 后，B 下游为空，但 Product 保存状态仍为 `ENABLED`；
6. 恢复 Store 后重新可见，receipt 历史可查询；
7. 全程 `allow_auto_send=false`。

截图由 E2E 生成在 Git 忽略的 `tests/e2e/test-results/`，不提交截图、数据库、日志或运行数据。

## 9. BUG-B-001 修复结果

`BUG-B-001` 在本候选版本中已修复并完成隔离浏览器验证：单条不兼容 C 数据不再导致 B 全目录 No data。根因修复位于 C 最终投影与 B 契约消费边界，没有在 B 增加可信度判断或修改正式业务数据。

状态：`FIXED_VERIFIED_CANDIDATE / PRODUCTION_RELEASE_PENDING`。正式 `AI-CS@42bafcf/0008` 仍运行旧版本，因此正式环境中的缺陷只有在独立授权完成 `0010` 备份/迁移、候选合入、Runtime 切换和业务验收后才能关闭为 Production Verified。

## 10. 未执行事项与下一 Gate

本任务未执行：

- 正式数据库备份或 `0010` migration；
- 正式 Runtime 停止、切换或重启；
- 正式业务数据初始化或运营启停；
- A、RAG、Prompt、R009 或 Import Center 变更；
- R003 正式业务验收和 R005 真实 Pilot 验证。

下一入口只能是独立的 R006 Production Release & Business Acceptance：先备份正式数据库，再在静默窗口迁移 `0010`、部署同一候选 SHA，验证四服务、TEST连续性、PILOT人工启用和 B 实际可见；失败时回滚 Runtime 和数据库备份。

最终状态：`R006_IMPLEMENTATION_COMPLETE`
