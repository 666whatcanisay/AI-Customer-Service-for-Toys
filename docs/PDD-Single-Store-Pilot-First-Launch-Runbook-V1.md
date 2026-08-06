# PDD Single Store Pilot First Launch Runbook V1

适用店铺：玩趣乐园积木店

安全模式：`PILOT / auto_reply=false / manual_approval=true / max 5 reservations per UTC day`

## 1. Hard Stop 条件

以下任一项未完成，不得登录或启用 real sender：

- [ ] 从 PDD 店铺后台和独立店铺资料双人核对真实 store ID；
- [ ] 用真实 store ID 替换 `pdd-store-id-must-be-verified`；
- [ ] credential provider 中创建专用 session reference，配置文件不含 cookie/token；
- [ ] 由人工确认 merchant chat HTTPS URL、authenticated path、login path；
- [ ] Store Identity selector contract 已从只读观察验证；
- [ ] 真实 inbound 协议/页面读取已形成版本化 adapter contract；
- [ ] 真实 sender endpoint、request、response 与“触发后 UNKNOWN”语义已验证；
- [ ] Global 和 PDD Kill Switch 现场演练通过；
- [ ] 数据库、Evidence 和日志备份位置已确认；
- [ ] 当班 operator 与第二复核人已记录。

## 2. 配置与启动

1. 复制示例 JSON 到节点专用路径；
2. 只替换经过核验的 store ID、credential reference；
3. 首次 Live 激活保持 `send_limit=1`、`approval_required=true`、`auto_reply=false`；
4. 校验 Channel Agent 与 Pilot 配置；
5. 先保持 Fake sender 和 Observation-only inbound；
6. 启动本地节点：

```powershell
$env:CHANNEL_AGENT_CONFIG_PATH = "C:\AI-CS\config\channel-agent.json"
$env:PDD_PILOT_CONFIG_PATH = "C:\AI-CS\config\pdd-pilot.json"
.\.venv\Scripts\channel-agent.exe
```

7. 仅从本机打开 `http://127.0.0.1:18020/pilot/ui`；
8. 记录 STARTUP Evidence。

期望：Node 尚未 READY，Today Send 为 `0/1`。

## 3. 人工登录

1. 点击“启动并打开人工登录”；
2. 确认 Chrome 使用专用 profile，不是用户默认 profile；
3. 人工检查地址栏为已核验 merchant chat HTTPS URL；
4. 人工扫码；系统不得填写密码、读取二维码或自动提交；
5. 点击“检查登录与店铺”；
6. 核对 Dashboard：

```text
Browser = CONNECTED
Store = 玩趣乐园积木店 / MATCHED
Safety = PILOT_MODE
```

若 Store 为 MISMATCH/UNVERIFIED，立即停止，不得通过修改配置去迎合当前页面。

## 4. Observation-only

1. 保持 real sender 未注入；
2. 接入经过验证的 receive-only PilotInboundPort；
3. 人工触发读取一条专用测试会话消息；
4. 检查 NormalizedMessage 的 message ID、conversation ID、timestamp；
5. 确认 Conversation/Decision/Evidence 保存后才 ACK；
6. 检查 AI answer 和 citations；
7. 不点击批准。

通过标准：Decision 为 WAITING_APPROVAL，sender 调用为 0，Today Send 为 0/1。

## 5. Dry Run

1. 使用内部测试会话；
2. 保持 Fake sender、`dry_run=true`、`allow_real_platform_transport=false`；
3. 人工复核店铺、conversation、answer、citations；
4. 点击“人工确认并执行”；
5. 检查 Execution、Receipt、Event、Outbox、Pilot Evidence；
6. Receipt 必须显示：

```text
real_platform_called = false
customer_message_sent = false
automatic_reply = false
```

7. 重复点击一次，确认返回原 Receipt 且额度不重复增加。

## 6. 单条真实发送窗口

此步骤需要独立批准并解决主报告 PILOT-001..005。不得仅通过配置文件开启。

1. 将经过验证的 real sender 注入 `PDDSendTransport`；
2. 代码级显式设置：

```text
dry_run = false
allow_real_platform_transport = true
```

3. 保持 send limit 为 5，但操作计划只批准 1 条；
4. 两人复核 store、conversation、reply、approval operator；
5. 一人点击批准，另一人观察 Dashboard 和 PDD 页面；
6. SUCCESS 必须有 PDD external message ID 和确认响应；
7. 任何 timeout/post-trigger uncertainty 进入 UNKNOWN，停止后续发送并人工核对；
8. 导出 Receipt/Evidence，确认 Today Send 为 1/5。

## 7. 扩展到最多 5 条

只有单条真实发送复盘通过后，才可逐条继续。每条都要求新的人工点击，不允许批量、
循环或自动批准。

到达 5/5 后必须阻断第六条；不得通过删除数据库行、改时钟或重置配置恢复额度。

## 8. Emergency Stop

出现以下任一情况立即启用 Kill Switch：

- Store mismatch；
- 页面/Selector drift；
- 重复消息冲突；
- AI answer/citation 异常；
- Receipt UNKNOWN；
- customer message 状态无法确认；
- Dashboard/数据库/Evidence 不一致。

操作：

1. `/pilot/kill-switch/enable`；
2. 确认 Safety=`KILL_SWITCH`、Channel=`BLOCKED`；
3. 停止 Pilot 和 Browser；
4. 保留数据库、profile、Receipt、Event、Outbox、Audit、Evidence；
5. 不自动重试 UNKNOWN；
6. 人工登录 PDD 核对实际消息状态；
7. 完成问题单和双人复核后才可解除；
8. 解除后必须重新执行 Check，不自动恢复发送。

## 9. Rollback

1. 启用 Kill Switch；
2. 停止节点；
3. 移除 real sender/inbound 装配，恢复 Fake/Dry Run；
4. 恢复最后已验证配置快照；
5. 不回滚或删除 Receipt/Evidence；
6. 启动后只执行 Observation-only；
7. 复盘完成前禁止真实发送。

## 10. Evidence Checklist

- [ ] STARTUP
- [ ] BROWSER_SESSION（人工登录）
- [ ] STORE_BINDING（MATCHED）
- [ ] MESSAGE_RECEIVED
- [ ] DECISION_CREATED（context/answer/citations）
- [ ] APPROVAL_GRANTED（operator）
- [ ] EXECUTION_STARTED（execution ID/attempt）
- [ ] RECEIPT_RECORDED
- [ ] Event + Outbox 一致
- [ ] Today Send 计数一致
- [ ] Kill Switch 演练 Evidence
- [ ] 明确标记 real/fake、dry-run/live

现场 Evidence 未收集前，不得将 `PDD_SINGLE_STORE_PILOT_READY` 描述为店铺已上线。
