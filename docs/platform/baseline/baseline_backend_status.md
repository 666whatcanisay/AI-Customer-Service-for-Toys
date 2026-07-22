# Platform backend 基线状态

## 已实现

- FastAPI 应用入口：`app.main:app`。
- `GET /health`：返回状态、服务名、版本和 request_id。
- request_id 中间件：接受可选 `X-Request-ID`，否则生成 UUID，并写回响应头。
- 统一错误体：HTTP、参数校验和未处理异常均使用 `error` 与 `request_id` 结构。
- 最小环境变量配置：服务名、版本、应用名和运行环境。
- pytest：健康响应、request_id 传递、404 错误结构。

## 已验证依赖

- Python 3.12.13
- FastAPI 0.139.2
- Uvicorn 0.51.0
- Pytest 9.1.1
- HTTPX 0.28.1

## 明确未实现

没有数据库、ORM、迁移、登录、JWT、Redis、Chroma、模型调用、RAG Client 或任何平台业务实体。当前服务仅是可运行骨架，不能视为生产就绪。
