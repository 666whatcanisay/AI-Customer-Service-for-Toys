# AI-CS Channel Execution Engine

AI-CS Channel Execution Engine 是 AI-CS 的独立执行层。AI-CS 负责 Decision、RAG、Knowledge 与 Model；Channel Engine 负责渠道运行、会话、人工审批、受控执行、Receipt、Outbox 与可观测性。

当前源码收口版本：Channel Engine `0.2.0rc2`，Channel Agent `2.0.0rc4`。

本版本的发布状态是 `RC4_OBSERVATION_FOUNDATION_CHECKPOINT`：离线回放、只读观察、Host 接收和 AI 建议链可验证；真实 PDD 页面证据与现场观察仍是独立 Gate，受控发送不在本版本范围内。

## 冻结边界

- Gateway Contract wire version：`1.0`
- Gateway Contract canonical SHA-256：`e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`
- Channel Engine 不生成 AI 回复。
- 未经人工 Approval 禁止 Execution。
- `UNKNOWN` 禁止自动重试。
- `real_send_enabled=false`，真实平台发送未启用。

## 环境

- Windows
- CPython 3.12
- SQLite

安装开发与验证依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-rc1.lock
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
```

执行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

仅启动本地受控 API：

```powershell
.\.venv\Scripts\python.exe -m uvicorn channel_engine.app:app --host 127.0.0.1 --port 18020
```

## 安全默认值

- Agent RC 默认 `kill_switch=true`。
- `manual_approval=true`。
- `auto_reply=false`。
- Credential 仅保存 reference，不保存 Cookie、Token 或密码明文。
- PDD、Sandbox 与 Fake 组件不能被解释为真实平台上线授权。

## 发布文档

- [RC1 Release Checklist](docs/releases/RC1-Release-Checklist.md)
- [RC1 Release Notes](docs/releases/RC1-Release-Notes.md)
- [RC1 Deployment Guide](docs/releases/RC1-Deployment-Guide.md)
- [RC1 Rollback Guide](docs/releases/RC1-Rollback-Guide.md)
- [RC1 Changelog](docs/releases/CHANGELOG-RC1.md)

架构说明见 [docs/architecture.md](docs/architecture.md)。
