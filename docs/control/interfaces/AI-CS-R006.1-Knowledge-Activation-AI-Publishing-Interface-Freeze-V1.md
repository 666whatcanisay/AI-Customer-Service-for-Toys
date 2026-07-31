# AI-CS R006.1 Knowledge Activation & AI Publishing Interface Freeze V1

> 冻结日期：2026-07-31  
> 基线：`AI-CS@b7783f759776ecf7592ae198893ba5100d75be08`  
> 任务分支：`feature/r006-1-knowledge-activation-v1`  
> 接口版本：`contracts 0.4.0`  
> 状态：`INTERFACE_FROZEN_FOR_R006_1`

## 1. 目标与所有权

本接口只补齐“商品知识已审核 → 客服可用 → AI可用”的两个独立人工动作。它不改变 R009 导入审核，不改变 R006 的 C Owner / B Consumer 边界，也不允许 A 判断商品是否可以进入客服目录。

| 能力 | Owner | Consumer | 冻结结论 |
| --- | --- | --- | --- |
| 商品审核状态与知识文档生成 | C | C Admin、A | 只有 C 生成当前已审核商品的规范文档和 fingerprint。 |
| 客服可用状态 | C | B | B 继续只消费 `/api/v1/customer-service/catalog/**` 最终投影。 |
| AI知识发布 | A | C | A只索引C提供的业务上下文，不执行权限判断。 |
| 商品级RAG可见性 | A | C Admin | A返回事实证据，C保存并展示生命周期状态。 |
| 运营动作与收据 | C | C Admin、审计 | C保存 publication receipt 和 activation receipt。 |

## 2. 冻结状态

AI知识状态只允许：

| 状态 | 含义 |
| --- | --- |
| `NOT_GENERATED` | 没有进入新发布链路，或当前集合没有该商品的新发布记录。 |
| `GENERATING` | C已受理，正在请求A生成切片和Embedding。 |
| `PUBLISHED` | 当前 fingerprint 与已索引 fingerprint 一致，chunks 与 embeddings 完整。 |
| `SYNC_FAILED` | A不可用、写入或校验失败；旧版本不得删除。 |
| `NEED_RESYNC` | 商品当前 fingerprint 与已发布 fingerprint 不一致。 |

客服状态仍为 `DISABLED / ENABLED`，资料审核仍由既有 `APPROVED` 控制。三种状态互不替代：客服启用不自动发布知识，AI发布也不自动启用客服。

## 3. C Admin接口

### 3.1 增量发布

`POST /api/v1/admin/product-knowledge/products/{product_id}/ai-publications`

Header：`Idempotency-Key`，必填且同键同请求可安全重放。

请求：

```json
{
  "operator": "运营账号",
  "confirmation_note": "人工确认发布当前已审核版本"
}
```

前置条件：商品存在、资料状态为`APPROVED`、`data_source`为`TEST`或`PILOT`。响应遵循`ai-product-knowledge-publication.v1`，包含状态、fingerprint、集合、chunk/embedding数量和发布收据。

### 3.2 可见性检查

`POST /api/v1/admin/product-knowledge/products/{product_id}/ai-publication-checks`

请求只包含`operator`。C调用A检查当前active collection中的商品级证据，保存检查时间、当前/已索引fingerprint、chunk数、embedding数和状态；检查不产生向量写入。

### 3.3 发布收据

`GET /api/v1/admin/product-knowledge/products/{product_id}/ai-publication-receipts`

只读返回该商品的发布收据，按时间倒序。收据至少包含：`publication_receipt_id`、`product_id`、`knowledge_fingerprint`、`active_collection`、`chunk_count`、`embedding_count`、`operator`、`created_at`。

### 3.4 批量客服启用

`POST /api/v1/admin/operations/products/customer-service-status:batch`

请求遵循`customer-service-catalog-batch-activation.v1`：

```json
{
  "product_refs": ["C-PRODUCT-..."],
  "customer_service_status": "ENABLED",
  "confirmed_by": "运营账号",
  "confirmation_note": "已审核商品批量启用"
}
```

只有资料状态为`APPROVED`的商品可以启用。单条失败必须隔离，成功、已是目标状态和失败逐条返回；每个实际变化复用R006已有activation receipt，不制造批次伪收据。

## 4. C → A内部接口

### 4.1 发布

`POST /api/admin/ai/knowledge-publications/products`

仅允许loopback调用。请求包含租户、平台、店铺、商品、数据来源、知识文档、fingerprint、source_ids、operator和idempotency_key。A不得检查`customer_service_status`，不得判断商品权限。

### 4.2 可见性

`POST /api/admin/ai/knowledge-publications/visibility`

支持商品列表检查，按`tenant_id + platform + store_code + product_id`查找active collection。返回`active_collection`、`chunk_count`、`embedding_count`、`indexed_fingerprint`、`current_fingerprint`、`updated_at`和发布状态。

## 5. 增量与失败规则

1. C以固定字段生成稳定、排序后的JSON文档并计算SHA-256 fingerprint，不调用LLM生成知识。
2. fingerprint未变化且已发布证据完整时返回`changed=false`，不重复向量化。
3. 新版本先完成切片、Embedding和回读校验，再删除同一商品的旧版本记录；其他商品和其他集合不受影响。
4. 发布失败时保留旧版本，C记录`SYNC_FAILED`和错误码，不把失败伪装成成功。
5. 客服状态变化不会触发向量化；知识内容变化通过fingerprint变为`NEED_RESYNC`；新商品首次发布走增量流程。
6. 不允许全量重建、自动发布、自动客服启用、Prompt修改或模型训练。

## 6. 数据库与兼容性

迁移`0011_product_knowledge_publishing_v1`在0010之后增加：

- `product_knowledge_publications`：每商品当前发布投影；
- `product_knowledge_publication_receipts`：不可覆盖的发布收据；
- `product_knowledge_publication_idempotency`：写请求幂等回放。

0010与此前表结构不修改；downgrade只删除0011新增表，不删除Chroma数据。`contracts 0.4.0`是相对0.3.0的纯新增版本，0.2.0/0.3.0 schema继续保留。历史TEST向量继续可检索，但没有新发布收据的历史商品在C新生命周期中显示`NOT_GENERATED`，避免伪造发布证据；运营可按商品显式进入新发布链路。

## 7. 安全边界

- `SUGGESTION_ONLY`、`AUTO_SEND_DISABLED`保持；
- 不自动发送消息、退款、改订单、写ERP；
- B不判断`test_data_mode`、`production_usable`、`publishable`；
- A不判断商品是否客服可用；
- 生产发布前必须单独完成数据库备份、0011迁移、Runtime同SHA和回滚演练；本实现任务不授权正式部署。
