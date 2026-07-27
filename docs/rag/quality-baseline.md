# AI 质量基线诊断

## 范围与边界

`GET /api/admin/ai/quality-baseline/latest` 只读取最新保存、标记为 `live_c_api` 的评测报告，并输出安全的 CASE 标识、检查项、分类信号与人工验证建议。它不运行模型、不访问 C、不修改 Prompt、知识、规则或模型，也不返回题目、回答、来源正文、事实文本、来源 ID、Prompt、密钥或平台地址。

该诊断是对已有评测证据的归因，不是新的线上评测，也不构成生产质量或安全认证。

## 当前真实基线

当前保存报告为 `a-t03-v031-live`：28 个 CASE 中 19 个通过（67.86%），9 个失败。

| 检查 | 通过数 | 结论 |
|---|---:|---|
| action | 28/28 | 没有动作选择失败证据。 |
| source_ids | 21/28 | 7 个 CASE 有来源归属检查失败。 |
| key_facts | 23/28 | 5 个 CASE 有关键事实检查失败。 |
| forbidden_claims | 28/28 | 没有禁用承诺失败证据。 |
| required_fields | 28/28 | 没有缺失字段决策失败证据。 |
| risk_level | 27/28 | 1 个 CASE 有风险等级决策不一致。 |
| scope | 28/28 | 没有范围泄漏失败证据。 |

失败 CASE 为：`007`、`009`、`011`、`019`、`020`、`021`、`022`、`023`、`026`（完整内部 CASE 标识由诊断 API 返回）。

## 归因方法

分类严格复用评测器记录的失败信号，允许同一 CASE 同时归入多个类，因此各类计数不可相加为失败总数。

- `DATA_PROBLEM`：`metadata_loss`。当前 9 个 CASE 均有直接信号，优先核验 C 导出、来源目录、范围和预期归属。
- `KNOWLEDGE_PROBLEM`：`key_facts` 不通过。当前 5 个 CASE 有直接信号，需人工比对冻结期望与受治理知识内容，不能补造事实。
- `RETRIEVAL_PROBLEM`：`retrieval_miss`。当前为 0；应在完成数据/归属核验后才重放同范围检索，不应先调阈值。
- `PROMPT_OR_MODEL_PROBLEM`：`model_expression_error`。当前为 0；没有证据支持自动或优先修改 Prompt。
- `RULE_DECISION_PROBLEM`：`structured_decision_error`。当前 1 个 CASE（含风险等级检查不一致），待数据归属核验后由治理方复核决策元数据。

## 人工优化建议

1. P0：核验 9 个 `metadata_loss` CASE 的 C 导出、来源目录与预期来源归属，确认数据缺失、关联范围或评测期望中的哪一项需要治理修订。
2. P0：核验 5 个关键事实失败 CASE 的冻结期望与受治理知识正文；不得通过补造知识、修改向量或改 Prompt 掩盖差异。
3. P1：在数据核验完成后，复核 1 个结构化风险决策不一致 CASE 的期望风险、知识元数据和规则口径。
4. P2：仅在上述核验后，对同一 frozen context 做检索重放，区分索引缺失和排序问题。
5. P2：保持 Prompt 冻结。只有将来出现 `model_expression_error` 且证据已充分时，才提交人工评审的 Prompt 变更提案。

所有建议都标记为 `automatic_change_allowed=false`；本任务不执行任何修复动作。
