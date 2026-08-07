# R027 AI-CS UX Acceptance Data Readiness V1 Task Card

- Requirement：`R027`
- Date：`2026-08-07`
- Owner：AI-CS Product Acceptance Data Engineer
- Target：`AI_CS_UX_ACCEPTANCE_DATA_READY`
- Status：`COMPLETE`

## Objective

关闭 R026 的三个环境级 P0：恢复三类初始化账号、增加普通客服验收账号、准备可检索且已发布的最小商品知识，从而允许四角色 UX 复验。

## Authorized data scope

- 当前受控 Runtime 的 IAM 账号、角色、Session 和客服 Store binding。
- 一个现有测试店铺下的一个现有商品、至少一个 SKU、至少五条经来源核对的客服 FAQ。
- 通过现有审核与发布状态机写入的知识版本、发布收据和增量向量。
- 数据写入前必须备份数据库和 RAG 资产并记录哈希；失败时恢复对应备份。

## Safety boundary

- 不修改 Gateway Contract、Channel Engine、PDD Adapter、Prompt、自动发送或数据库 Schema。
- 不直接写密码哈希，不绕过认证；密码只经现有 IAM hash/service/API 处理。
- 不使用真实客户信息，不把密码、hash、token、数据库、向量、日志、知识源或备份提交 Git。
- 不清空、覆盖或全量重建既有向量库；仅允许现有受控增量发布流程。

## Acceptance criteria

1. `admin`、`Wa`、`江`及普通客服验收账号均为 ACTIVE、角色正确，并通过真实登录和退出验证。
2. 普通客服仅有 CUSTOMER_SERVICE 权限，至少绑定一个测试店铺，可进入 Workspace，不能访问运营管理接口。
3. 一个商品、至少一个 SKU 和五条以上 FAQ 经审核并发布；活动 Collection 非空且 chunk 数大于 0。
4. 问题“这个积木缺件怎么办？”返回 AI 建议、知识依据和风险提示；不自动发送。
5. 输出《AI-CS UX Acceptance Data Readiness V1》，记录备份、变更、验证和回滚方法。
