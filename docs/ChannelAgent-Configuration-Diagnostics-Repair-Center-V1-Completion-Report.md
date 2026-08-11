# ChannelAgent 配置、诊断与一键修复中心 V1 完成报告

版本：ChannelAgent 1.6.0

## 完成范围

- 正常登录页保持简洁，快速预检仅展示运行状态和“运行配置”入口。
- 只有 `BLOCKED` 自动展开双栏诊断中心；`WARNING` 不阻断客服流程。
- 诊断覆盖 Agent、配置、AI-CS、Channel Engine、身份绑定、店铺、Edge、PDD Session、本地代理及永久安全锁。
- 登录错误区分 401、429、AI-CS 地址缺失、502/503/504、Channel Engine 身份拒绝和未知故障编号。
- 本地配置采用字段白名单、同源限制、人工意图头、连通性校验、原子写入、上一版备份和失败回滚。
- 一键修复按固定顺序执行，限制一小时最多三次；需要连接码、扫码、验证码或授权变更时停留人工处理。
- 配置重载使用独立 `reload.request`，保留 Edge 独立 Profile 和 PDD Session，不执行浏览器关闭。
- Windows 托盘检测受控重启标记，旧 Runtime 停止后再启动新 Runtime 并恢复助手窗口。

## 本地 API

- `GET /local-api/v1/doctor`
- `GET /local-api/v1/config`
- `POST /local-api/v1/config/validate`
- `PUT /local-api/v1/config`
- `POST /local-api/v1/repair`
- `GET /local-api/v1/repair/{repair_id}`
- `POST /local-api/v1/onboarding/discover`
- `POST /local-api/v1/onboarding/pair`

所有写操作仅允许 loopback 同源；配置和修复分别要求
`HUMAN_CONFIRMED_CONFIGURATION`、`HUMAN_CONFIRMED_REPAIR`。

## 永久安全边界

- `manual_approval_required=true`
- `auto_reply_enabled=false`
- `real_send_enabled=false`
- `real_platform_activation_allowed=false`

配置接口拒绝密码、Cookie、Token、Secret、私钥及非白名单字段。

## 验证结果

- Channel Engine：632 passed，1 个显式 Edge smoke 测试按环境跳过。
- AI-CS 前端：40 个文件、175 个测试全部通过。
- TypeScript 类型检查和 ChannelAgent 专用前端构建通过。
- Windows 1.6.0 ZIP 构建通过。
- 原位升级验证保留 config、身份绑定和既有 Edge 进程。
- 实机诊断准确显示 AI-CS/Channel Engine 健康；当前设备未绑定被识别为 `CHANNEL_ENGINE_IDENTITY_UNBOUND`，未误报密码。

## 已知限制

- 设备绑定、连接码、PDD 扫码和验证码仍必须人工完成。
- 一键修复不会变更用户、店铺、设备授权或生产安全开关。
- 未执行真实 PDD 登录、消息读取或发送。
