# AI-CS 商品回答风险池完整知识闭环 Card 8 完成报告

日期：2026-08-14

Gate：`PASS / AI_CS_PDD_REPLY_READINESS_KNOWLEDGE_LOOP_READY / SOURCE_ONLY`

## 交付结果

- C 在创建评测时自动冻结当前商品的最新已审核资料；SKU 评测额外纳入精确 SKU 资料，不读取其他 SKU。
- 每个 `material_id` 只取最新有效审核修订；运营可显式选择一份 `RECOGNIZED / REVIEWING` 修订，替换同一资料身份的已审核版本作为本次草稿覆盖。
- 全部来源写入现有运行 `input_json`，运行行上的 `material_id/revision` 继续只表示草稿覆盖；未新增表、后台任务或 `KnowledgeMaterial` 列。
- A 同时消费多份商品知识、SKU 差异、FAQ 和安全规则，保留跨资料冲突，不以优先级静默覆盖；逐题只引用实际提供答案、事实或安全规则的资料。
- FAQ 优先使用 `关联问题ID`；旧 FAQ 仅在标准问法或别名规范化后完全相等时命中。旧安全规则只提供禁止声明约束，不能主动降低风险。
- `/reply-readiness` 明确展示自动聚合与可选草稿覆盖，每题可按首要缺口跳转现有 `/knowledge-editor`；保存新修订后返回会携带并选择该修订复跑。

## 安全与兼容

- `effective_risk` 继续受问题政策底线、真实 Router/Quality Gate 和资料缺口共同约束；库存、价格、物流、退款、改地址和真伪等题不能因补资料变成低风险。
- 30cm/40cm、多资料不同确定值、估测值、跨商品/SKU、拒绝/分析失败资料和重复资料身份均 Fail Closed。
- SKU 的数量/尺寸区别只进入 `variant_difference`，不会被当作该 SKU 的精确颗粒数或成品尺寸。
- 候选 `PddReplyReadinessInputV1` additive 增加 `knowledge_sources[]`；原 `knowledge_snapshot` 继续可解析，两者同时出现时拒绝。
- 正式 Contract 保持 `0.14.0 / coordinated`；Gateway Wire 1.0 及冻结 Schema 原始 SHA-256 `fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80` 不变。

## 验证证据

- A 任务范围与 Router 汇总：`43 passed`。其中直接读取 C 的 36 题基线，并由真实 `ReplyReadinessEvaluator + ReplyRouter` 完整执行，36/36 均生成结果。
- C 任务范围与迁移保护：`11 passed`。覆盖最新有效修订、商品/精确 SKU 聚合、其他 SKU/拒绝资料排除、草稿替换、冻结输入、幂等及 `KnowledgeMaterial` 无迁移。
- Admin 全量：`37 files / 104 tests passed`；`vue-tsc --noEmit` 与 production build 通过。
- 候选 Schema/Fixture 生成漂移检查通过；新多来源和旧单来源 Fixture 均由 A/C 严格类型解析。
- Alembic 单一源码 Head 仍为 `0023_reply_readiness_v1`；`git diff --check` 通过。

## 运行边界

- 未启动服务，未访问或占用正式端口，未访问正式数据库、向量库、DataRoot、PDD Profile 或扫码窗口。
- 未修改 Engine、CE、PDD、生产 RAG、真实发送或主动欢迎入口。
- 所有评测继续固定 `test_data_mode=true`、`production_usable=false`、`allow_auto_send=false`。

`AI_CS_ENTRY_CONTEXT = DEFERRED_CROSS_REPO`

本 Gate 只代表 AI-CS 源码中的商品知识补充与隔离风险复跑闭环完成，不代表真实 PDD、自动发送、Pilot 或 Production Ready。
