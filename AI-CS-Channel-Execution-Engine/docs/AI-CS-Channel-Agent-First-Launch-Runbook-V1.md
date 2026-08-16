# AI-CS Channel Agent First Launch Runbook V1

## 1. 安装流程

1. 在受支持的 Windows 电脑安装 Channel Agent。
2. 安装 Google Chrome。
3. 确认 AI-CS Server 已由运维人员启动。
4. 启动 Channel Agent 本地服务。
5. 打开本地入口 `/agent`。

首次使用会自动进入 First Launch Wizard。不要编辑本地配置文件，也不要向任何页面粘贴 token、cookie 或密码。

## 2. 第一次启动

1. 在欢迎页确认平台为“拼多多商家聊天”。
2. 点击“开始环境检查”。
3. 查看 Environment Doctor：
   - `PASS`：可继续。
   - `WARNING`：通常表示等待登录、Profile 尚待创建或 Kill Switch 已开启。
   - `BLOCKED`：必须先修复。
4. Doctor 通过后，系统自动创建独立 Workspace 并进入等待登录页。

系统不会要求填写 `store_id`、credential、cookie、token 或密码。

## 3. 登录流程

1. 确认页面显示：
   - Chrome：`OPEN`
   - Profile：`pdd-pilot-single-store-001`
   - Login：`WAITING`
2. 在独立 Chrome 窗口内由用户人工扫码。
3. 不要在 Channel Agent 页面输入账号或密码。
4. 登录完成后点击“检查登录状态”。
5. 系统只读验证会话并发现店铺身份。
6. 店铺匹配后自动生成 StoreBinding。

若窗口意外关闭，点击“重新打开浏览器”。该按钮只重新打开专用窗口，不执行自动登录。

## 4. Ready 确认

Ready 页面必须显示：

```text
Browser: CONNECTED
Session: VALID
Channel: READY
AI: READY
Safety: PILOT MODE
Approval: REQUIRED
```

确认 Node 和 Store 名称正确后，点击“进入运行控制台”。

Ready 不代表自动回复已开启。所有发送能力仍受 Approval、Execution、Kill Switch 和 Safety Gate 控制。

## 5. 异常处理

### AI-CS 连接失败

- 提示：`AI-CS 连接失败`
- 操作：确认 AI-CS 服务启动并恢复 Gateway Health，然后点击“修复后重新开始”。

### Chrome 启动失败

- 提示：`Chrome 启动失败`
- 操作：检查 Chrome 安装和本地 Profile 权限，不要改用默认 Chrome Profile。

### 登录失败

- 提示：`拼多多登录未完成`
- 操作：重新打开浏览器并再次人工扫码。

### 无法确认店铺

- 提示：`无法确认店铺身份`
- 操作：确认浏览器已进入商家聊天页，再检查登录状态。

### Store mismatch

- 提示：`店铺不匹配`
- 结果：Agent 停止，已有绑定不会被覆盖。
- 操作：退出错误店铺，使用正确店铺重新扫码。

### Kill Switch 已开启

- 提示：`Kill Switch 已开启`
- 结果：允许查看诊断，但禁止进入 Ready。
- 操作：仅由授权人员在确认安全后处理 Kill Switch。

## 6. 关闭流程

1. 进入 `/agent/ui`。
2. 点击“停止节点”。
3. 确认 Node、Browser 和 Channel 状态为 `STOPPED`。
4. 关闭本地控制台页面。

停止节点不会删除 Profile、历史 Receipt、Event 或 Audit。

## 7. 重新绑定店铺

1. 在 Ready 页面点击“重新绑定店铺”。
2. 阅读确认提示。
3. 确认后，系统停止 Agent 并仅移除由向导创建的本地绑定。
4. 重新执行 Environment Doctor。
5. 打开独立 Chrome 并人工扫码。
6. 系统重新只读确认店铺身份。

若失败原因是 Store mismatch，修复后重试不会自动覆盖原有可信绑定。

## 8. 禁止事项

- 不自动登录。
- 不导出 Cookie。
- 不读取真实客户消息。
- 不发送真实消息。
- 不开启自动回复。
- 不手填店铺 ID。
- 不绕过 Manual Approval 或 Kill Switch。
