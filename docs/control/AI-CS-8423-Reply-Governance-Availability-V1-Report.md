# 8423 商品回答风险池与知识编辑器正式可用闭环 V1

日期：2026-08-15

Gate：`CANDIDATE_VALIDATED / AI_CS_8423_REPLY_GOVERNANCE_DEPLOYMENT_PENDING`

本报告会在同一候选提交完成 8423 运行验收后更新为最终 Gate。当前状态只证明源码、数据库备份和隔离闭环已经通过。

## 已完成

- 简洁模式直接显示“商品回答风险池”和“知识编辑器”；两项统一要求 `knowledge.manage`，ADMIN、OPERATOR 可见，普通客服不可见且直达路由会进入无权限页。
- 高级模式不再重复展示入口；长期地址固定为 `http://127.0.0.1:8423/reply-readiness` 与 `http://127.0.0.1:8423/knowledge-editor`。
- 临时 15174 地址和 `ui.architect` 验收账号不进入正式部署；正式数据库不创建临时用户。
- 当前 R027 数据库在部署前已经是唯一源码 Head `0023_reply_readiness_v1`，因此本轮不重复迁移。在线备份完整性为 `ok`，数据库实例身份摘要保持可核对，两张 Readiness 表均存在。

## 验证证据

- A 全量：`239 passed, 3 skipped`；C 全量：`216 passed`。
- Admin：`40 files / 114 tests`，typecheck 与 production build 通过。
- 完整 36 题经真实 `ReplyReadinessEvaluator + ReplyRouter` 返回 `36/36`；隔离 C→A 真实 HTTP 返回 `SYNTHETIC_C_TO_A_REAL_HTTP_OK`。
- Readiness 候选兼容、数据库迁移/身份专项、Gateway raw/canonical SHA 冻结检查通过。
- Contract 保持 `0.14.0 / coordinated`；Gateway Wire 保持 `1.0`。

## 待完成的运行验收

- 从单一 clean 候选提交受控重启 8420–8423，并确认四服务身份一致。
- 用现有超级管理员在 8423 简洁模式进入两页，确认真实目录、四种模板、36 题与单条只读调试可用。
- 正式验收不保存占位知识、不触发 Approval、Authorization、Execution、Sender 或真实发送。

## 边界

- 不停止或修改 18443、60801，不访问 PDD Profile，不修改 Engine、Agent 或真实发送状态。
- 风险池和调试继续固定 `production_usable=false`、`allow_auto_send=false`。
