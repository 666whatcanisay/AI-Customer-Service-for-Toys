# Channel Agent Production Service Identity V1

日期：2026-08-07

状态：`CHANNEL_AGENT_PRODUCTION_SERVICE_IDENTITY_READY`

## 1. 目标

为AI-CS Platform Backend的客服设备Facade提供受控服务身份，使其可以读取Agent状态并签发
一次性Enrollment Grant，同时保持Channel Engine默认Deny-All。本能力不连接PDD、不读取消息、
不启用浏览器控制，也不允许发送。

## 2. 配置与认证

- 配置键：`CHANNEL_ENGINE_AGENT_OPERATOR_SESSION_FILE`。
- 配置值是外部Runtime文件的绝对路径，不是会话引用本身。
- 文件必须是UTF-8单行不透明引用，长度至少32字符且不超过4096 bytes。
- Channel Engine启动时读取文件并只保留SHA-256摘要；认证使用常量时间摘要比较。
- 原始引用不写入源码、环境变量、状态、响应、审计或日志。
- 未配置文件时继续使用`DenyAllOperatorIdentityProvider`。
- 路径相对、文件缺失、编码或格式错误时启动失败；错误引用返回403。

## 3. 权限边界

服务身份只注入Channel Agent Node Router。它不注入PDD、Execution、Approval、Gateway或其他
Channel Engine控制面。现有`X-Operator-Session-Reference`Header和Agent Protocol 1.0保持
不变，因此没有Gateway Contract或Agent Contract变更。

生产部署必须同时满足：

1. 服务只监听loopback，或远程场景使用HTTPS。
2. 引用文件仅允许运行账号与SYSTEM读取。
3. AI-CS只在Platform Backend进程内读取引用，浏览器永远不可见。
4. Enrollment后仍需独立管理员激活；服务身份不会自动绑定或自动激活设备。
5. 引用轮换后受控重启两侧Runtime，不允许双引用长期并存。

## 4. 验证

- 正确外部引用：Agent Admin list返回200。
- 错误引用：返回403 `OPERATOR_PERMISSION_DENIED`。
- 未配置：默认Deny-All保持不变。
- 引用文件缺失、相对路径、多行或过短：拒绝启动。
- Provider内存对象不保留原始引用。
- 全仓回归：559 passed，0 failed，1个第三方弃用警告。
- Contract回归：123 passed，0 failed，1个第三方弃用警告。
- `pip check`与`compileall`：PASS。

## 5. 不变边界

- Gateway Contract V1未修改。
- Agent Protocol 1.0未修改。
- PDD Adapter未修改。
- `message_read_enabled=false`。
- `send_enabled=false`。
- `browser_automation_enabled=false`。

Final Status：`CHANNEL_AGENT_PRODUCTION_SERVICE_IDENTITY_READY`
