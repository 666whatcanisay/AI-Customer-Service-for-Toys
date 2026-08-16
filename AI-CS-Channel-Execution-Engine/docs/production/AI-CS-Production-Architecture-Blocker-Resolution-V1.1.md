# AI-CS 生产架构阻塞项修复 V1.1 完成报告

## 1. 结论

- 软件收敛候选：`PASS`
- ChannelAgent：`2.0.0rc1`
- Channel Engine：`0.2.0rc1`
- Agent Control Contract：`channel-agent-control.v2.1`
- Gateway Contract：`1.0`，canonical SHA-256 保持 `e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`
- 真实平台决策：`BLOCKED`
- 真实平台副作用：`0`

本轮完成了软件架构、EXE边界、安全发送、V2.1控制协议、Windows RC包和Synthetic闭环的收敛。真实PDD仍未登录、未观察、未读取客户消息、未发送。阻塞原因是本轮安全边界禁止接触真实PDD，因此无法产生由人工验证、绑定真实页面指纹且未过期的Production Selector Evidence。

## 2. 架构收敛

冻结运行链：

```text
PDD
→ ChannelAgent Edge
→ Channel Engine Host Control
→ AI-CS
→ 人工审批
→ Channel Engine签发ExecutionAuthorization
→ ChannelAgent受控Transport
→ Receipt回传
```

职责已经按以下边界收敛：

- ChannelAgent：设备、独立Browser Profile、PDD边缘边界、短缓存、桌面UI、V2.1客户端、受控执行和Receipt暂存。
- Channel Engine：注册、心跳、店铺策略、审批、Lease、Execution Authorization、Kill Switch、Receipt和恢复。
- AI-CS：RBAC、店铺权限、CustomerContext、商品/SKU/订单业务数据、RAG、LLM、Decision、长期数据和业务审计。

生产Host使用独立最小入口，不挂载V1、Fake、Sandbox、Discovery或Pilot路由。旧实现未删除：仍被历史链使用的标记为`ACTIVE_LEGACY`，旧导入兼容入口标记为`COMPATIBILITY_SHIM`，确认无运行依赖的标记为`ARCHIVE_READY`。本RC只建立归档清单，不移动或删除未知资产。

## 3. EXE能力与包边界

生产composition使用25个显式源码allowlist。2.0.0rc1包内`channel-agent.pyz`共27个条目：

- V1/legacy模块名：0
- `channel_engine`、`ai_cs`、Fake、Sandbox、Discovery、Pilot：0
- RAG、LLM、知识库和长期业务存储：0

边缘消息顺序固定为：

```text
捕获并脱敏
→ DPAPI加密短暂存
→ Host事务持久化
→ Host返回ACK
→ Agent推进Cursor
```

ACK前允许重复投递；相同消息ID但内容不同会Fail Closed。Agent仅保留未ACK事件、Cursor和默认30分钟短缓存，AI-CS仍是长期业务数据源。

Windows RC产物：

- `dist/windows-client-v2/AI-CS-Channel-Agent-2.0.0rc1-windows-x64.zip`
- SHA-256：`5d201a873a0be8691ce98b61a6161e2791819900f3263b32442a1d148ed43cfc`

## 4. 安全发送链

### UNKNOWN Receipt

内部Receipt事实字段统一为：

- `transport_triggered: true | false | null`
- `customer_message_sent: true | false | null`
- `confirmation_state`
- `reconciliation_required`

Transport触发后结果无法确认时，发送事实为`null`而不是虚假`false`；状态保持`UNKNOWN`，禁止自动重试，重启后仍进入人工核对。UNKNOWN不再被标记为Fake。

### Execution Authorization

每次边缘执行必须验证服务端签名授权，覆盖agent、device、store、conversation、customer、decision、approval、execution、lease、最终回复Hash、send key、policy版本、Selector Evidence Hash、nonce和过期时间。

执行前继续强制：人工审批、有效Lease、Kill Switch关闭、页面主体一致、allowlist/risk/rate limit、Activation Grant和Selector Evidence。直接采用、编辑采用和人工输入使用同一安全链；采用记录不再冒充发送成功。

### Selector Evidence

唯一Evidence Store已经建立。VERIFIED记录必须包含页面指纹、Selector集合、能力边界、验证证据、验证人、时间、失效时间、页面版本和Evidence Hash。代码不能直接声明Production VERIFIED；页面指纹变化、Evidence缺失或过期时执行为零。

## 5. Agent Control V2.1

生产LAN只挂载`/channel-agent/v2`；所有已知`/channel-agent/v1`路径在Production Host均返回404。

V2.1实现：

- 设备域与AI-CS服务域使用独立密钥。
- HMAC覆盖method、path、timestamp、nonce和body hash。
- 重放、过期、错设备和错店铺Fail Closed。
- Enrollment Grant只持久化一次性Hash，重启可恢复，消费后失效。
- AI-CS `ChannelAgentUpstream`使用签名V2.1接口。
- 非loopback Host必须使用TLS；私钥必须为加密PKCS#8，口令从Windows Credential Manager读取，ACL仅允许运行账户和SYSTEM。
- 口令不进入命令行、环境变量或日志。

Gateway Contract V1未增删字段、未改业务语义。

## 6. 验证结果

| 验证 | 结果 |
| --- | --- |
| Channel Engine全量回归 | `669 passed, 1 skipped` |
| Engine Contract | `123 passed` |
| Engine Security | `17 passed` |
| V2.1 Synthetic/Authorization/UNKNOWN/Selector专项 | `14 passed` |
| AI-CS Platform Backend | 全量通过（160项） |
| AI-CS客服前端 | `42 files / 190 tests passed` |
| AI-CS前端typecheck | PASS |
| AI-CS Agent专用build | PASS；保留既有大chunk warning |
| AI-CS Backend | `150 passed, 3 opt-in real E2E skipped` |
| Gateway跨仓验证 | `10/10 PASS`，全部Fail Closed |
| Python compileall | PASS |
| 三个Python环境pip check | PASS |
| 两仓git diff --check | PASS；仅既有LF/CRLF提示 |

跨仓验证确认：schema对象、生成模型和原始Gateway Schema一致；HMAC Health、Decision、trace、幂等重放、冲突、401、403、超时UNKNOWN和非法Schema均符合冻结Contract。

Synthetic完整链已覆盖：模拟消息持久化后ACK、Conversation/CustomerContext、AI Decision、桌面助手、人工确认、签名执行授权、Synthetic Transport和Receipt。真实平台调用数、真实客户读取数和真实发送数均为0。

## 7. 安全配置

最终安全锁保持：

```text
manual_approval_required=true
auto_reply_enabled=false
real_send_enabled=false
real_platform_activation_allowed=false
```

未发现包内明文Secret依赖；设备与服务认证隔离。测试中使用的Synthetic密钥只存在于测试夹具，不进入生产composition。

## 8. 升级、回滚与清理

- 升级保留Agent Identity、Device、游标、Edge Profile和PDD Session。
- 配置原子写入，失败恢复上一份已验证配置。
- 数据库变化采用additive migration；历史Receipt不删除。
- 重复模块先归档，不直接删除；未知untracked资产只排除，不清理。
- 旧V1客户端升级后必须重新可信配对。
- 本轮未执行Git提交、暂存或Source Freeze；两个仓库仍为dirty worktree，因此“干净checkout可重复发布”必须在后续Source Freeze任务中再次验证。

## 9. Real PDD Activation Gate

已通过：

- UNKNOWN事实语义和重启不重试。
- Production V1路由关闭。
- V2.1设备/服务认证。
- EXE与生产composition一致。
- Synthetic闭环和失败场景。
- Gateway冻结SHA。
- Security/Contract/Regression。

仍阻塞：

- 尚无真实页面人工验证的Production Selector Evidence Hash。
- 尚未在clean checkout上完成同一包的Source Freeze重建与签名发布。

因此当前只能声明软件收敛候选通过，不能声明`READY_FOR_CONTROLLED_PILOT`，更不能激活真实PDD。下一步应在人工在场、只读窗口和Kill Switch就绪条件下执行Selector Evidence采集；通过后再从clean Source Freeze重新构建同一协调RC。
