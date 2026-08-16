# AI-CS Channel Agent Dashboard V1

## 1. 产品定位

Channel Agent Dashboard V1 是运行在单台 Windows 节点上的本地控制台。它把已有 Agent Runtime、Browser Runtime、Store Binding 与 Safety Gate 投影为面向操作人员的统一状态视图，同时只复用既有 `start`、`check`、`stop` 生命周期操作。

本版本不提供消息编辑、审批、发送、退款或订单操作入口，不修改 PDD Transport、AI-CS Gateway、Decision 或 Execution 业务链。

## 2. 页面结构

`GET /agent/ui` 提供响应式本地控制台，包含：

- Dashboard Home：Agent、Node、AI-CS、Browser、Channel 与 Safety 总览。
- Store Binding：店铺名称、店铺标识与 `CONNECTED / WAITING_LOGIN / DISCONNECTED` 状态。
- Browser Status：Chrome、独立 Profile、Session 与 Login 状态。
- Safety Panel：Runtime Mode、Pilot Mode、Manual Approval 与 Kill Switch。
- Runtime Timeline：最近 12 条启动、连接、登录检查、状态更新、异常和停止事件。
- Runtime Controls：启动、立即检查、停止；仅调用已有 Agent 生命周期 API。

控制台无第三方前端依赖，不加载远程字体、脚本或图片。所有运行态字段通过 `textContent` 写入 DOM，避免把店铺名称或运行原因当作 HTML 执行。

## 3. Dashboard API

新增：

```http
GET /agent/dashboard
Accept: application/json
```

返回 `ChannelAgentDashboard`：

- `agent`：总体健康、Ready、版本、环境。
- `node`：节点标识、名称、状态、最近心跳。
- `ai_cs`：组件状态、连接状态、Endpoint、原因码。
- `browser`：Chrome 状态、Profile、Session、Login、原因码。
- `channel`：平台、组件状态与原因码。
- `store`：绑定身份与产品连接态。
- `safety`：Runtime Mode、Pilot Mode、Manual Approval、Kill Switch、Dry Run。
- `timeline`：按时间倒序的最近生命周期事件。
- `config_fingerprint`：不含明文凭据的配置指纹。

响应不包含 `agent_token_reference`、`credential_reference`、cookie、token、secret 或客户消息。

## 4. 状态投影规则

### Store Binding

| 条件 | Dashboard 状态 |
|---|---|
| 未绑定、绑定暂停或 Agent 已停止 | `DISCONNECTED` |
| 已绑定，Browser/Channel 尚未同时健康 | `WAITING_LOGIN` |
| 已绑定且 Browser、Channel 均健康 | `CONNECTED` |

### Browser 与 Login

| 条件 | Session | Login |
|---|---|---|
| Agent 尚未启动 | `NOT_STARTED` | `DISCONNECTED` |
| Agent 已停止 | `STOPPED` | `DISCONNECTED` |
| Browser 不可用 | `DEGRADED` | `WAITING_LOGIN` |
| Browser 健康，但缺少完整渠道证据 | `ACTIVE` | `UNKNOWN` |
| Store 已绑定且 Browser、Channel 均健康 | `ACTIVE` | `AUTHENTICATED` |

该规则不会仅根据 Chrome 进程存在就宣称登录成功。

## 5. Timeline

Dashboard 将既有 `AgentLifecycleEvent` 映射为只读产品事件：

- `ENVIRONMENT_CHECK / CONFIG_LOAD` → `STARTUP`
- `SERVER_CONNECT / CHANNEL_CHECK` → `CONNECTION`
- `BROWSER_CHECK` → `LOGIN`
- `READY` → `STATUS`
- `STOP` → `STOP`
- 任意失败事件 → `ERROR`

Timeline 不新增业务事件写入，不记录凭据、客户消息或页面内容。

## 6. 安全边界

- `manual_approval=true` 固定显示为 REQUIRED。
- `send_control_available=false` 是 Dashboard V1 合约常量。
- Kill Switch 只显示权威运行状态；本版本不增加切换入口。
- UI 不包含 `/send` 或 `/approve` 调用。
- 页面刷新只执行 `GET /agent/dashboard`，不会自动启动节点。
- 所有 PDD、AI-CS、Gateway 与 Execution 实现保持不变。

## 7. 测试结果

新增测试覆盖：

- 产品页面与全部面板渲染。
- `/agent/dashboard` API 合约与敏感引用不泄露。
- Agent 启动后的健康、Store、Browser、Safety 与 Timeline 投影。
- Browser 不可用时的 `WAITING_LOGIN` 与错误事件。
- Agent 停止和 Store 未绑定时的 `DISCONNECTED`。
- AI-CS 不可用时的 fail-closed 状态。
- 页面不包含发送或审批操作入口。

执行结果：

```text
Targeted: 15 passed, 1 warning
Full suite: 268 passed, 1 warning
```

Warning 来自既有 Starlette `TestClient` 对 httpx 兼容层的弃用提示，不影响测试通过。

## 8. 完成状态

`CHANNEL_AGENT_DASHBOARD_READY`
