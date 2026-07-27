# MVP-PLUS-02-B-C-SMOKE: B-C 真实联调记录

日期：2026-07-27
历史结论：`BLOCKED`（无代码、UI 或共享契约修改）。后续 `MVP-PLUS-02-B-CONTRACT-ADAPT` 已在同日修复 B consumer 并通过真实验证；本记录仅保留初始阻断证据。

## 受控验证环境

- C 当前分支以隔离 SQLite 数据库启动；`GET /health` 返回 HTTP 200。
- 所有载荷均为合成、去标识化测试内容；五种类型均覆盖：`FACT_ERROR`、`MISSING_INFO`、`STYLE_ISSUE`、`RISK_ISSUE`、`OTHER`。
- 测试进程已停止。隔离数据库目录位于本机临时目录，因本机执行策略拒绝删除命令而保留；其中只含本次合成 smoke 数据，未进入仓库。

## POST 结果

| 请求形态 | 结果 | 证据 |
| --- | --- | --- |
| 当前 B client 的实际请求形态（未发送 `Idempotency-Key`） | 五类均为 HTTP 422 | C 返回 `AI_RESPONSE_FEEDBACK_VALIDATION_FAILED`，指出缺少 `Idempotency-Key`；前端不显示本地成功。 |
| 冻结协议的直接探针（每类均携带唯一 `Idempotency-Key`） | 五类均为 HTTP 201 | 每个响应均含非空 `feedback_id` 且 `status=NEW`。 |

当前 C 的 HTTP 201 创建回执只含 `feedback_id`、`status`。当前 B 的严格 adapter 还要求 `analysis_status=NEW` 与合法 `created_at`，因此即使补上请求头，B 仍会将该回执判为契约失败并且不会伪造成功。

## GET 结果

`GET /api/v1/ai-response-feedback?created_by=B-SMOKE-20260727&status=NEW&page=1&size=20` 返回 HTTP 200、`total=5`、`items=5`。五个创建的反馈记录均存在，且每项为 `status=NEW`、`analysis_status=NEW` 并有 `created_at`。

## 阻断与后续

端到端页面提交不能标记为通过：B 缺少 C 已要求的幂等键，C 创建回执又缺少 B 已冻结的两个字段。需要经共享契约版本化、兼容性说明和受影响线路评审后，统一 B 请求头与 C 创建回执；本任务不实施该变更。
