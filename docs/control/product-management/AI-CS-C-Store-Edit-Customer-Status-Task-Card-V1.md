# AI-CS C Store Edit Customer Status Task Card V1

- 任务ID：`C-STORE-EDIT-CS-STATUS-V1`
- 日期：2026-07-31
- Owner：C Admin
- 基线：`AI-CS@0c118080137a2ab55cea47fdbddaf418ec05c7e1`
- 分支：`feature/c-store-edit-customer-status-v1`

## 目标

在“店铺管理 → 编辑店铺”表单中展示并允许修改“客服使用状态”。状态变更继续调用现有 R006 激活接口，要求填写操作人并生成 activation receipt。

## 范围

- 修改 `admin_web/src/views/StoreManagementView.vue`。
- 补充 `admin_web/tests/StoreManagementView.spec.ts`。
- 更新 C 状态、变更、交接和 machine-context。

不包含：

- 不修改 C Backend、数据库、migration 或 contracts。
- 不修改 A、B、RAG、Prompt 或 R009。
- 不批量启用店铺下的商品；Store 与 Product 继续独立人工确认。
- 不自动发送消息、发布知识、退款、修改订单或写入 ERP。

## 成功标准

1. 编辑店铺时可看到当前“已启用/已禁用”状态。
2. 状态发生变化时，未填写操作人不得保存。
3. 保存时复用现有 `setStoreCustomerServiceStatus`，使用幂等键并展示收据。
4. 状态未变化时不调用激活接口；新增店铺继续由后端默认 `DISABLED`。
5. Admin Vitest、typecheck、build 和浏览器验收通过。

## 风险与缓解

- 店铺资料更新与客服状态是两个既有接口：UI 必须区分部分失败，并且不得谎报状态已经修改。
- 启用 Store 不会改变 Product 状态：页面必须保留明确边界提示。
- 正式数据状态只能由用户实际提交表单时改变；开发和自动测试使用 mock/隔离环境。

## Gate

完成前：`C_STORE_EDIT_CUSTOMER_STATUS_IN_PROGRESS`

完成条件：`C_STORE_EDIT_CUSTOMER_STATUS_READY`
