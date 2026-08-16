# Channel Engine RC1 Deployment Guide

## 1. 前置条件

- Windows 10/11 x64。
- CPython `3.12.x`。
- 待部署源码必须来自 RC1 受保护提交或其签名归档。
- Gateway Contract canonical SHA 必须等于冻结值。
- 禁止使用真实 PDD Credential；配置只允许 Credential Reference。

## 2. 安装

在独立目录创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-rc1.lock
.\.venv\Scripts\python.exe -m pip install . --no-deps
```

验证版本与合同：

```powershell
.\.venv\Scripts\python.exe -c "import channel_engine; print(channel_engine.__version__)"
.\.venv\Scripts\python.exe scripts\verify_channel_engine_rc1.py --regression-evidence evidence\channel-engine-rc1\regression-results.json
```

只有 Gate 返回 `READY` 才允许继续。

## 3. 配置

- Runtime 默认使用 Mock/Staging。
- SQLite 文件放入受控 runtime 目录，并纳入备份。
- Credential 仅配置 provider reference。
- AI-CS客服设备Facade需要访问Agent管理接口时，使用
  `CHANNEL_ENGINE_AGENT_OPERATOR_SESSION_FILE`指向Runtime外部UTF-8单行引用文件；
  禁止把引用值写入环境变量、源码、命令行或日志。
- 未配置上述文件时Agent管理接口保持Deny-All。文件缺失、格式错误或引用不匹配时
  必须启动失败或返回403，禁止回退到测试身份提供方。
- `manual_approval=true`。
- `auto_reply=false`。
- 首次启动保持 Kill Switch ENABLED。
- 不配置真实平台 endpoint、Cookie、Token、密码或客户数据。

## 4. 启动

仅绑定 loopback：

```powershell
.\.venv\Scripts\python.exe -m uvicorn channel_engine.app:app --host 127.0.0.1 --port 18020
```

客服设备服务身份只注入`/channel-agent/v1/admin/*`所在的Agent Router。部署时应为引用文件
设置仅运行账号与SYSTEM可读的ACL；轮换引用后需要受控重启Channel Engine与AI-CS Platform
Runtime。普通浏览器、Agent配置和API响应不得获得该引用。

## 5. 验证

```powershell
Invoke-RestMethod http://127.0.0.1:18020/health
Invoke-RestMethod http://127.0.0.1:18020/runtime/v1/status
```

必须确认：

- `production_enabled=false`
- `real_channel_enabled=false`
- `browser_execution_enabled=false`
- `human_approval_required=true`
- `unknown_auto_retry_enabled=false`
- `automatic_send_enabled=false`

## 6. 停止

使用运行宿主的正常终止机制发送 Ctrl+C 或服务停止信号，等待 lifespan 完成 Adapter、Session、Worker 与数据库连接的关闭。不要直接删除 SQLite、Receipt、Outbox 或 Audit 文件。

## 7. 发布后验证

- 再次检查 `/health` 与 Runtime 状态。
- 验证 Kill Switch 保持启用。
- 验证无 PDD 连接、无客户消息、无 Execution 和无发送。
- 保存运行版本、commit、合同 SHA 与配置快照，不保存任何凭据材料。
