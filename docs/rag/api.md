# API 文档

除兼容路由外，标准响应格式为：

```json
{
  "success": true,
  "message": "ok",
  "data": {}
}
```

聊天接口同时保留顶层 `answer` 和 `sources`，便于兼容旧客户端。

## GET /api/health

进程健康检查。RAG 尚未就绪时仍返回 HTTP 200，`data.ready=false`。

## GET /api/status

返回：

- `ready`：本地 RAG 是否就绪。
- `message`：初始化进度或错误。
- `model_configured`：百炼 Key 是否已配置。
- `initialization_error`：初始化错误摘要或 `null`。

## GET /api/knowledge/statistics

返回 PDF 数、向量块数、Embedding 模型、Chroma collection 和模型配置状态。

兼容路由：`GET /api/stats`。

## GET /api/questions/recommended

返回客服页面的推荐问题列表。

## GET /api/config/model

仅允许从本机访问。返回服务商、模型名称、是否已配置、配置保存位置及是否需要重启，不返回 API Key 或其掩码片段。

## PUT /api/config/model

仅允许从本机访问。首次配置请求：

```json
{
  "provider": "bailian",
  "model": "qwen-turbo",
  "api_key": "填写本机密钥"
}
```

已配置时省略 `api_key` 可只更新模型名称；传入 `"clear_api_key": true` 可清除密钥。配置会原子写入 `backend/.env` 并即时应用，响应永不包含 Key 明文。

## POST /api/chat

请求：

```json
{
  "message": "党员有哪些义务？"
}
```

响应 `data`：

```json
{
  "answer": "...",
  "sources": [
    {
      "file": "党员章程.pdf",
      "page": 1,
      "distance": 0.249,
      "content_preview": "..."
    }
  ],
  "model_configured": false,
  "elapsed_ms": 12.3
}
```

空问题返回 HTTP 422。服务初始化失败或尚未完成时返回 HTTP 503。Key 为空但检索命中时仍返回 HTTP 200 和来源。

## POST /api/retrieval/search

请求：

```json
{
  "query": "党员义务",
  "top_k": 2
}
```

返回是否通过距离阈值、阈值值、最小距离及来源列表，不调用大模型。

## 旧页面兼容路由

- `GET /api/ai/status`
- `GET /api/ai/stats`
- `POST /api/ai/chat`

这些路由使用原 Java 代理的 `{code, message, data}` 外层结构。
