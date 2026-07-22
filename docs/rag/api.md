# API 文档

标准响应使用 `{success, message, data}` 外层；聊天结果同时保留在顶层以兼容既有客户端。

## GET /api/health

进程健康检查。RAG 尚未就绪时仍返回 HTTP 200，`data.ready=false`。

## GET /api/status

返回 `ready`、`message`、`model_configured` 和 `initialization_error`。

## POST /api/retrieval/search

请求：`{"query":"Nebula Fox indicator color","top_k":1}`。响应 data 含 `accepted`、`threshold`、`top_distance` 与 `sources`，不调用 LLM。

## POST /api/chat

请求：`{"message":"What color is the Nebula Fox safety indicator?"}`。

响应 data 至少包含：

```json
{
  "answer": "...",
  "action": "ANSWER",
  "sources": [
    {
      "source_name": "synthetic-nebula-fox.pdf",
      "page": 1,
      "chunk_id": "...",
      "distance": 0.217,
      "excerpt": "..."
    }
  ],
  "model": "qwen3.5:9b",
  "latency_ms": 845.3,
  "request_id": "..."
}
```

低置信或无结果时返回 `action=REFUSE`、固定受控拒答文案和空 `sources`。空问题返回 HTTP 422；RAG 初始化未完成或失败时检索与聊天返回 HTTP 503。

其他既有路由包括知识统计、推荐问题、本机模型配置和 `/api/ai/*` 兼容路由；A-T02 未改变共享 contracts。
