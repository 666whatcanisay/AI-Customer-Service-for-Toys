# AI-CS Channel Execution Engine

AI-CS Channel Execution Engine 是一个独立的、clean-room 实现的渠道执行层基础工程。

它与现有系统保持明确边界：

- **AI-CS**：智能决策层，负责知识、RAG、模型、决策和反馈。
- **Channel Engine**：执行层，负责会话接入、人工批准、受控执行、回执和事件账本。
- **Starboat**：仅作为能力参考，不是依赖，也不被接管。

Foundation V1 只提供Fake Channel、Fake Gateway和Fake Execution。它不会连接真实AI-CS，不会启动真实浏览器，不会向任何客户发送消息。

## 安全原则

1. 所有建议默认等待人工批准。
2. 未批准Decision禁止执行。
3. `UNKNOWN` Execution禁止自动重试，必须人工核对外部状态。
4. Execution Receipt和Event只追加，不覆盖历史。
5. 业务事件与Transactional Outbox在同一SQLite事务中保存。

## 快速开始

要求Python 3.12。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

启动Foundation API：

```powershell
.\.venv\Scripts\python.exe -m uvicorn channel_engine.app:app --host 127.0.0.1 --port 18020
```

可用的Fake API：

- `GET /health`
- `POST /v1/fake-channel/messages`
- `GET /v1/decisions/{decision_id}`
- `POST /v1/decisions/{decision_id}/approve`
- `POST /v1/decisions/{decision_id}/reject`

## 当前非目标

- 拼多多或其他真实渠道接入
- Playwright真实页面操作
- 自动发送消息
- AI模型或AI-CS真实Gateway调用
- 自动退款、订单修改或资金操作

架构详情见 [docs/architecture.md](docs/architecture.md)。
