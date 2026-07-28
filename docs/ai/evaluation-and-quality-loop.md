# AI 评测与质量闭环

## 原则

AI-CS 采用“人工确认的数据 → 受控 AI 分析 → 人工评估建议”的闭环。AI 分析结果只能作为优化依据，不能自动训练、改 Prompt、发布知识或执行客户/ERP 操作。

## 两类客服沉淀

### 客服经验案例

B 提交案例到 C 后，C 负责保存与审核：

`NEW → REVIEWING → APPROVED`，或 `NEW → REJECTED`

`APPROVED` 的案例必须生成不可变快照；内容修改要建立新 revision，不能覆盖旧版本。A 只消费已批准且去标识化的快照，并在评测结果中记录 `case_id`、`revision`、`evaluation_run_id`、`model_version`、`prompt_version`、结果与建议，随后回写 C 供运营查看。

### AI 回答问题反馈

B 将未采用的 AI 回答及分类提交给 C；C 的处理状态为：

`NEW → ANALYZING → ANALYZED`

只有已确认、具备 revision 和 content hash 证据的反馈才能进入 A 的分析输入。A 返回分析运行标识、模型版本、Prompt 版本、问题分类和建议；C 保存后在 AI 问题/优化池展示。Badcase 统计只能来自这类显式、有效的反馈与评测数据，不能凭页面状态或猜测生成。

## 知识质量闭环

受控资料先由 C 识别和人工审核，进入 `APPROVED_FOR_ANALYSIS` 后才可由 A 分析。A 返回缺口、风险、建议与可追溯证据；C 展示质量池。这个过程没有“自动发布”分支，客服端仅消费紧凑的只读准备度信息。

## 可追溯性要求

每个分析结果应能关联输入对象的 ID、revision、内容校验、分析运行 ID、模型版本和 Prompt 版本。接口调用的成功语义、错误码、幂等和兼容性以以下冻结文档为准：

- [AI 控制中心接口](../control/interfaces/ai-control.v1.md)
- [知识质量闭环接口](../control/interfaces/knowledge-quality-loop.v1.md)
- 经验案例与 AI 反馈接口文档（`docs/control/interfaces/`）

跨 A/B/C 修改接口前，Control 的 Interface Owner 必须重新审查所有者、Provider/Consumer、字段、状态、错误码、幂等和版本兼容性。
