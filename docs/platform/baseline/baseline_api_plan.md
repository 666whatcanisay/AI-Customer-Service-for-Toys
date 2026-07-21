# API 基线与后续计划

## 本轮已实现

`GET /health`

成功响应：

```json
{
  "status": "ok",
  "service": "platform-backend",
  "version": "0.1.0",
  "request_id": "..."
}
```

请求可携带 `X-Request-ID`；响应体和响应头返回同一值。错误响应统一为：

```json
{
  "error": {
    "code": "HTTP_404",
    "message": "Not Found"
  },
  "request_id": "..."
}
```

该接口只服务当前 C 线管理端基线，不修改共享 OpenAPI 或 Schema。

## 后续任务边界

商品、知识、反馈、评测、审核、发布和 RAG 集成接口全部留待 C-T02 及后续任务。新增跨线字段时必须先更新 schema、版本、CHANGELOG、兼容性说明并完成受影响线路审查；本轮不提前定义或实现这些接口。
