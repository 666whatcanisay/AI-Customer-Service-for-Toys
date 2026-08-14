# AI-CS PDD 回答就绪度 Reuse First 矩阵 V1

日期：2026-08-14

任务：任务卡 7「PDD 回答优化与商品风险调整池 V1」

## 结论

本卡复用现有知识、范围、规则、Router、证据和鉴权能力，只新增问题集扩展与评测运行两张任务专用表。`knowledge_materials` 核心表零列变更，正式数据库未迁移。

| 需要的能力 | 复用位置 | 本卡处理 | 是否新增核心框架 |
|---|---|---|---|
| STORE / PRODUCT / SKU 范围 | `TestProduct.store_code/product_id`、`TestSku.sku_id`、既有店铺访问校验 | PRODUCT 使用 `store_code + product_id`；SKU 再绑定 `sku_id`；SKU 资料不能用于商品级运行 | 否 |
| 冻结会话与范围 | A 的 `FrozenChatContext`、`VerifiedProductContext`、`ReplyRouter` | 每题生成精确的合成 `ReplyTurnEnvelopeV1`，范围来自 C 冻结输入 | 否 |
| 知识不可变修订 | `KnowledgeMaterial(material_id, revision, content_hash)` 和全部历史行 | 增加历史列表、指定修订详情、字段 Diff 和模板 JSON 回填；保存仍创建 `revision+1` | 否 |
| 商品回答字段 | 既有 `analysis_text` 模板 JSON | 扩充颗粒、尺寸、比例、重量、兼容、安装、发货地、资料状态、禁止承诺和人工条件等模板字段 | 否；无数据库列 |
| 固定回复治理 | 现有 ReplyRule 审核、发布、完整快照和来源修订证据 | 运行绑定当前 `snapshot_revision + snapshot_fingerprint`；A 再校验当前快照 | 否 |
| 固定/RAG/组合路由 | `ReplyRouter.decide()`、Quality Gate、`reply_evidence_bundle.v1` | A 使用真实 Router 和内存 Replay Provider，保存来源类型、引用身份和证据包哈希 | 否 |
| RAG 隔离 | 现有范围校验和 Router RAG Provider 接口 | 草稿只进入内存 Provider，不写正式向量库、RAG 发布或 Gateway | 否 |
| 问题集 | 无等价版本化评测投影 | 新增全局 36 类脱敏基线及 STORE/PRODUCT 只增不减扩展投影 | 是；任务专用 |
| 运行账本 | 现有幂等、回执和内容哈希模式 | 新增冻结输入、结果哈希、失败状态、比较和一次运行回执 | 是；任务专用 |
| 内部服务鉴权 | 既有文件令牌、loopback 校验和 no-proxy 本地客户端 | C Admin 调 C；C 服务端调用 A 内部接口；浏览器不传 A 证据 | 否 |
| Admin 治理入口 | 现有商品知识、审核队列和资料编辑器 | 新增 `/reply-readiness`，并复用现有编辑器/审核/知识治理跳转 | 否 |

## 明确不做

- 不给 `KnowledgeMaterial` 增加 STORE/PRODUCT/SKU 新列。
- 不建立第二套审核、发布、权限、向量库或知识数据库。
- 不把评测问题发布到 RAG，不把草稿审核或发布。
- 不调用 Engine、CE、PDD、Channel Agent 或发送链路。
- 不实现主动欢迎、商品卡或订单卡入口。

如果未来需要正式 STORE 级知识来源，必须拆成独立任务卡，重新评审来源治理、范围表达和迁移，不在任务卡 7 中临时扩张。
