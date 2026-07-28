# PILOT-USER-IDENTITY-V1：C 端客服身份与来源追溯

> 状态：C 端实现完成，等待与 B 身份选择页面联调。
> 范围：内部试运行；不是密码认证、SSO 或正式 RBAC。

## 1. 面向运营的能力

运营中心新增“客服用户”页面，可在已导入的店铺资料基础上：

- 新增客服、运营或管理员身份；
- 修改姓名、角色、可处理店铺和默认店铺；
- 启用或停用客服；
- 查看每个身份绑定的店铺。

客服用户停用后，工作台不能再选择该身份，也不能以该身份提交新的经验案例、AI 问题反馈或效率事件。历史记录不会被删除。

## 2. C 端数据与校验边界

`CustomerUser` 由 C 生成不可猜测的 `CSU-*` 用户标识，并保存：显示名称、试运行角色、启停状态、默认店铺及店铺绑定。B 只能读取已启用的身份，不能在浏览器本地创建身份。

现有 `CustomerExperienceCase.created_by` 与 `AIResponseFeedback.created_by` 现在必须是一个已启用的 C 用户标识，且该用户必须绑定所选店铺。无效身份、已停用身份或未绑定店铺会由 C 拒绝；旧的自由文本测试身份不再能绕过该校验。

效率事件新增为独立的 `CustomerEfficiencyEvent`。它只记录事件类型、客服用户标识、店铺、商品/SKU、一次性会话/交互标识和可选反馈 ID；**不保存客户原文、AI 回答、最终回复、订单号、地址、手机号或设备信息**。C 对事件顺序、反馈归属和 `Idempotency-Key` 做校验，避免重复计数。

## 3. 接口

冻结设计见 [`customer-identity.v1.md`](../control/interfaces/customer-identity.v1.md)（随 Interface Owner Draft PR 交付）。C 实现的路径为：

- B 身份选择：`GET /api/v1/customer-identities`、`GET /api/v1/customer-identities/{user_id}`；
- C 用户管理：`GET/POST /api/v1/admin/customer-users`、`PUT /api/v1/admin/customer-users/{user_id}`、`POST /api/v1/admin/customer-users/{user_id}/status`；
- 效率事实写入：`POST /api/v1/customer-efficiency/events`。

这次没有修改 `contracts/**`。`customer-efficiency.v1` 的冻结事件模型沿用既有 Interface Owner 文档；B 的事件发送实现必须与该文档的字段、幂等和隐私边界一致。

## 4. 数据库迁移与回滚

迁移 `0007_pilot_user_identity` 增加：

- `customer_users`；
- `customer_user_store_bindings`；
- `customer_efficiency_events`；
- `customer_efficiency_event_idempotency`。

已在一个新建的隔离 SQLite 测试库执行 `upgrade head` 和降级回 `0006_mvp_plus_02_ai_feedback_idempotency`；迁移创建和移除的表均已核验。不得对未知数据库执行回滚。

## 5. 已验证与后续依赖

- 平台完整 pytest：通过；
- 用户管理、身份/店铺校验、案例/反馈来源校验、效率事件顺序与幂等专项测试：通过；
- Admin 用户管理页：typecheck、专项 Vitest 和 production build 通过；
- 浏览器真实流程仍依赖 B 的登录/身份选择实现和最终 C/B 集成环境。

## 6. 明确不做的事

本能力不提供密码、登录凭证、SSO、生产级权限、员工绩效排名、客户内容采集、自动评价客服、自动发送消息、自动退款、订单/ERP 写入、自动改 Prompt、自动发布知识或自动训练。
