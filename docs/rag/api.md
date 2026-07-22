# API 文档

## POST /api/chat

新规范请求固定为 question + context；context 只接受 `TENANT-PDD-SM-TEST / pdd / PDD-SM`。

响应 `data` 固定包含：`answer`、`action`、`risk_level`、`sources`、`warnings`、`required_fields`、`model`、`latency_ms`、`request_id`、`context`。sources 固定包含 `source_name`、`page`、`chunk_id`、`distance`、`excerpt`、`knowledge_version`、`source_ids`、`product_id`、`sku_id`。

旧 `{message}` 请求仍可用于原 A-T02 客户端，但不得携带 context；B-T03 只消费 data。

## POST /api/retrieval/search

支持 `query/top_k/context`，使用与 chat 相同的 tenant、店铺、商品、SKU 范围过滤，不调用 LLM。

## POST /api/test-knowledge/sync/{package_id}

仅允许本机调用。从配置的 C 地址获取 `version=V0.3.1`、`schema_version=0.3.1-test` 的 rag-export，严格验证后写入独立测试 Collection。未配置或服务不可用返回 `503 ENV_BLOCKED`，不合格包返回 422。

原 `/api/health`、`/api/status`、统计、配置和 `/api/ai/*` 兼容路由继续保留。
