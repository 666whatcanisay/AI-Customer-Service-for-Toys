# 《AI-CS PDD Single Store Pilot Live Report V1》

报告时间：2026-08-04（Asia/Shanghai）
目标店铺：玩趣乐园积木店
目标状态：`PDD_SINGLE_STORE_PILOT_LIVE`
本次真实预检结果：`PDD_SINGLE_STORE_PILOT_ACTIVATION_BLOCKED`

## 1. 结论

本次已完成本机只读 Live Preflight、Live 激活专用安全闸门、单消息/单回复控制、
UNKNOWN 自动停机、机器可读证据和 API/测试。预检没有启动新的 Chrome、没有复用用户
现有 Chrome、没有读取真实客户消息、没有调用真实 PDD 发送。

当前不能诚实声明 `PDD_SINGLE_STORE_PILOT_LIVE`。硬阻断包括：Channel Agent 未运行、
真实 `store_id` 未提供、Pilot 数据库未初始化、权威 Kill Switch 状态不可读、真实页面
Selector Contract 未验证、入站与出站仍为 Fake、AI-CS 的签名 Gateway Health 路径当前
返回 404。任何一项存在时，`POST /pilot/live/start` 都会在启动 Chrome 前返回 409。

## 2. 真实运行架构

```mermaid
flowchart LR
    A["Channel Agent"] --> B["Live Preflight Gate"]
    B --> C["Dedicated Chrome Profile"]
    C --> D["Human QR Login"]
    D --> E["Read-only Store Identity Probe"]
    E --> F["Real Receive-only Inbound"]
    F --> G["NormalizedMessage"]
    G --> H["Signed AI-CS Gateway V1"]
    H --> I["Decision: WAITING_APPROVAL"]
    I --> J["Human Approval"]
    J --> K["Execution + Lease"]
    K --> L["Controlled Real PDD Sender"]
    L --> M["Immutable Receipt + Event"]
    M --> N["Live Evidence Gate"]
```

Live 状态只由最后的 Evidence Gate 产生，不能由配置布尔值、Fake 成功结果或人工口头确认
直接赋值。Gate 要求真实浏览器代次、精确店铺匹配、恰好一条入站消息、恰好一次执行，
以及同时包含 `outcome=SUCCESS`、`real_platform_called=true`、
`customer_message_sent=true` 的 Receipt。

## 3. Live Preflight

| 检查项 | 结果 | 现场证据 |
| --- | --- | --- |
| System Chrome | PASS | `chrome.exe` 存在，版本 `151.0.7922.71` |
| Agent Status | BLOCKED | `127.0.0.1:18020` 无监听 |
| Runtime Storage | BLOCKED | `.runtime/channel-engine.sqlite3` 无任何表，WAL 为 0 bytes |
| Live Config | BLOCKED | 四个 Agent/Pilot 环境变量均未配置 |
| Safety defaults | PASS | `auto_reply=false`、`approval_required=true`、`send_limit=1` |
| Kill Switch | BLOCKED | 运行库未初始化，无法取得权威持久状态 |
| Store Binding | BLOCKED | `store_id=pdd-store-id-must-be-verified` 仍为占位值 |
| Dedicated Profile | BLOCKED | `C:/AI-CS/ChannelAgent/profiles` 尚未创建 |
| Merchant Chat URL | PARTIAL | 星船静态配置给出 `https://mms.pinduoduo.com/chat-merchant/index.html`；登录/已认证路径规则未验证 |
| Selector Contract | BLOCKED | `pdd:merchant_chat:v1` 仍为 DRAFT，未从真实页面取证 |
| Real Inbound | BLOCKED | 当前组合为 `FakePilotInboundPort` |
| AI-CS Gateway | BLOCKED | `/api/health` 为 200，但 `/gateway/v1/health` 为 404；未完成签名健康检查 |
| Real Outbound | BLOCKED | 当前组合为 `FakePDDHTTPSender` |

本机另有 19 个 Chrome 进程和监听 8001 的外部 `DigitalService.exe`。它们不是本任务创建
或拥有的资源，因此未附着、未关闭、未复用，也不能作为独立 Profile 或 Live 证据。

完整无敏感值证据见
`evidence/PDD-Single-Store-Pilot-Live-Preflight-Evidence-V1.json`。

## 4. 启动流程

Live 专用入口：

1. `GET /pilot/live/preflight` 获取全部 PASS/BLOCKED 检查；
2. 仅在全部 PASS 时允许 `POST /pilot/live/start`；
3. 创建专用 profile，不附着用户默认 Chrome；
4. 打开经证据确认的 merchant chat HTTPS URL；
5. 进入 `WAITING_FOR_LOGIN`，系统不输入账号、密码或验证码；
6. 人工扫码后调用 `POST /pilot/live/check`；
7. 只读验证 Browser、Session、Store、Channel、AI-CS；
8. 任一项未知或错店立即 Fail Closed。

当前第 1 步返回 BLOCKED，因此本次没有执行第 2 步，避免在缺少店铺身份规则和真实端口
时启动不可验证的浏览器会话。

## 5. 登录与 Session 验证

合格 Session 必须同时满足：

- Browser 为 `CONNECTED`，且 `real_browser_started=true`；
- `generation >= 1`，记录 `page_revision` 和 `selector_version`；
- 登录状态由已验证的 URL/页面规则只读判断；
- Store ID 与 Store Name 都精确匹配 Pilot 配置；
- Session 只引用 `credential_reference`，Evidence 不含 cookie/token/secret；
- Channel 与 AI-CS 健康后才设置 Runtime 为 `READY`。

`PilotBrowserObservation` 已扩展记录 generation、page revision 和 selector version；Fake
Browser 即使返回 CONNECTED，也不能通过 Live Preflight 的 real-browser 检查。

## 6. 消息链路

Live 消息入口为 `POST /pilot/live/messages/poll`。激活服务在进程内和持久 Evidence 两层检查
消息数量；一旦已记录一条 `MESSAGE_RECEIVED`，第二条消息会以
`PILOT_LIVE_MESSAGE_LIMIT_REACHED` 阻断。

保存的入站证据只包括：

- 内部 message ID；
- external message ID；
- conversation ID；
- timestamp；
- store ID；
- payload summary（channel、content length、sender present）。

Evidence 不保存客户消息正文。AI-CS 返回后保存 Decision ID、建议答案、citations、risk、
action、gateway version，并明确记录 `state=WAITING_APPROVAL`。本阶段不存在自动批准路径。

## 7. 发送链路

Live 发送唯一入口为：

`POST /pilot/live/decisions/{decision_id}/approve`

请求必须带人工 operator，并且 Decision 必须绑定本次唯一入站消息。随后仍由现有链执行：

`Decision -> Approval -> Execution -> Lease -> Safety Gate -> Transport -> Receipt`

额外约束：

- 配置必须是 `send_limit=1`；
- `auto_reply=false` 与 `approval_required=true` 为类型级常量；
- API 不提供 `/pilot/live/send` 或裸文本发送入口；
- 重复同一批准返回原执行/Receipt；不同 Decision 被拒绝；
- Receipt 为 FAILED 时不宣告 LIVE；
- Receipt 或 Execution 为 UNKNOWN 时立即打开 Kill Switch、停止 Runtime，并记录
  `LIVE_STOPPED`；禁止自动重试。

## 8. Evidence 与状态判定

`GET /pilot/live/report` 汇总以下持久证据：

1. STARTUP；
2. BROWSER_SESSION；
3. STORE_BINDING；
4. MESSAGE_RECEIVED；
5. DECISION_CREATED；
6. APPROVAL_GRANTED；
7. EXECUTION_STARTED；
8. RECEIPT_RECORDED。

只有上述证据齐全、消息与执行各恰好一次、Browser/Store/Runtime 仍为安全状态，且真实
Receipt 完整证明发送成功时，报告才返回 `PDD_SINGLE_STORE_PILOT_LIVE`。Offline/Fake
链路即使执行结果为 SUCCESS，也因 `real_platform_called=false` 被判定为 BLOCKED。

## 9. 故障处理

| 场景 | 动作 |
| --- | --- |
| Store mismatch | Kill Switch ENABLED，停止 Runtime，不读取/发送 |
| WebSocket/Inbound UNKNOWN | Kill Switch ENABLED，停止 Runtime，不 ack 未持久化消息 |
| Send UNKNOWN | 保存 UNKNOWN Receipt，Kill Switch ENABLED，停止，不重试 |
| 登录过期 | Runtime 退出 READY，等待人工重新登录 |
| AI-CS 不可用/超时 | 不创建 Approval/Execution，不发送 |
| 第二条消息或第二个 Decision | Live 激活闸门拒绝 |

## 10. 测试结果

定向测试：`21 passed, 1 warning`。

新增覆盖：

- Fake 默认组合不能通过 Live Preflight；
- Preflight 失败时不会调用 Browser start；
- Offline 完整 Receipt 不能冒充 LIVE；
- Send UNKNOWN 会打开 Kill Switch、停止 Runtime；
- Live API 暴露 Preflight/Report，但没有裸 send endpoint；
- 首次激活默认发送上限收紧为 1。

warning 来自 FastAPI TestClient 对旧 httpx 适配层的弃用提示，不影响业务断言。

## 11. 恢复激活所需输入与顺序

恢复前只需要提供引用和事实，不应在聊天或配置文件中提供 secret/cookie/token：

1. 玩趣乐园积木店的已核验 PDD `store_id`；
2. 可解析的 opaque `credential_reference` 和独立 profile root；
3. 人工操作员在场，可扫码并核对页面上的店铺身份；
4. 已验证的登录/已认证路径和 Store Identity selector contract；
5. 可用的真实 receive-only adapter、受控 sender 和签名 AI-CS Gateway V1。

完成这些条件后，按
`docs/PDD-Single-Store-Pilot-First-Launch-Runbook-V1.md` 从 Preflight 重新开始。首次真实
发送前必须再次展示 Decision、目标会话、店铺、风险和发送内容，且只接受一次人工确认。

## 12. 最终状态

本次代码与安全控制已为 Live 激活建立可验证边界，但没有真实登录、真实消息、真实
Decision 或真实 Receipt。依据“不得伪造现场证据”的规则，本报告最终状态为：

`PDD_SINGLE_STORE_PILOT_ACTIVATION_BLOCKED`

不得将其替换为 `PDD_SINGLE_STORE_PILOT_LIVE`，直到 `GET /pilot/live/report` 在真实现场
返回该状态。
