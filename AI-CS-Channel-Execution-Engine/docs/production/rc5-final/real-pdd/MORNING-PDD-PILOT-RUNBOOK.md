# Morning PDD Pilot Runbook

## 0. 安全边界

用户手工登录/扫码/选会话；程序不保存密码、Cookie、Token，不调用私有接口。开始与结束均确认 `REAL_SEND=OFF`。发生多窗口、错店、错会话或 Selector 不唯一时立即停止并截图，不猜测。

## 1. 当前绿色助手人工收口（先做）

1. 确认只有一个要验收的绿色助手窗口；不要使用 Windows 自动点击猜 URL。
2. 用 Synthetic/Replay 进入一条消息，核对客户消息、商品/SKU、AI 回复、风险和知识依据。
3. 点击“人工确认并准备执行（不发送）”。
4. 后端核对 Decision → Approval → `EXECUTION_PREPARED`，内容 Hash 一致。
5. 核对 `RealExecutionAttempt=0`、`RealSend=0`、`RealReceipt=0`。
6. 通过后记录 `CURRENT_GREEN_UI_HUMAN_ACCEPTANCE=PASS` 与 `RC5_FINAL_READY=PASS`。

## 2. 人工启动专属 PDD Edge

1. 在绿色助手点击专属 PDD 启动入口。该动作必须由人触发。
2. 若出现登录/扫码页，由用户人工完成；不导出 Cookie。
3. 若先进入管理平台，用户手工打开 `https://mms.pinduoduo.com/chat-merchant/index.html#`。
4. 到达客服工作台后，点击“我已进入客服工作台，重新识别”。
5. 等待 READY；若店铺不唯一、页面不是客服工作台或识别失败，停止并截图。
6. 若观察会话已到期，点击“重新开始30分钟观察”。按钮不得改变 real read/send 开关。

## 3. Gate 顺序

### REAL_PDD_ADAPTER_READY

- 唯一 Edge/Profile/客服工作台；登录和店铺身份识别。
- DOM/iframe/虚拟列表/Selector Evidence，缺失或多匹配 fail-closed。
- PDD Snapshot → REAL_PDD Observation → Spool → Host → ACK；Cursor 仅在 ACK 后推进。

### REAL_PDD_READ_READY

前置：`ADAPTER_READY=PASS`。用手机测试买家依次发送：唯一标识单条、三条连续短消息、多轮追问、商品/SKU问题。核对 message ID、CUSTOMER/OPERATOR、顺序、会话、商品与 SKU。订单/物流/售后为独立 Gate，不阻塞核心读取。

取得第一个完整会话后立刻：脱敏 → 扫描 → Fixture SHA → 审批 Sidecar → Approval Registry 锚点 → 离线 Replay 等价测试。原始数据删除或受控隔离。

### REAL_PDD_AI_READY

核对真实 Observation、CustomerContext、真实页面 history、AI、Quality Gate 与绿色助手；UI/Decision Hash 一致；重放不重复 Decision；`REAL_SEND=OFF`。

### REAL_PDD_CONFIRM_READY

保持 `MANUAL_CONFIRM`；人工确认生成唯一 Approval/ExecutionPrepared；不触碰 PDD 发送按钮，无 Real Receipt。

### REAL_PDD_SEND_READY（独立、最后、可选）

只在前置 Gate 全 PASS 后按最终验证计划执行单条人工确认受控发送。任何 UNKNOWN 禁止自动重试。

## 4. 退出检查

- Pending Spool 与 Cursor/ACK 一致。
- 原始 Evidence 无账号、Cookie、Token 和未脱敏个人数据。
- RealSend 状态与 Real Receipt 增量符合本次 Gate。
- Identity、Binding、Profile 路径、Store 授权未改变。
- Observer 到 30 分钟停止采集；已持久化 Observation 可等待 ACK。继续时由用户重新启动。
