# 《AI-CS Customer Desktop Workflow Integration V1 Completion Report》

## 结论

- Requirement：`R022`
- Gate：`PASS / SOURCE_ONLY`
- Final Status：`AI_CS_CUSTOMER_DESKTOP_WORKFLOW_READY`
- 结论边界：源码、共享契约、隔离测试和受控Runtime配置已经就绪；正式数据库仍为0013，0014/0015未部署，生产Channel Agent未配置或联通，未执行真实第二台客服电脑E2E。

## 1. 页面变化

Customer Workspace保留Conversation Center、AI Reply Assistant、Decision Center三栏，在其上方增加“客服电脑连接”状态区：

- 当前客服：来自C的Bearer session，不从浏览器自报身份。
- 当前店铺：来自Store Context的有效授权Store。
- 当前设备：显示匹配的device id/hostname，不展示其他用户或Store设备。
- Agent状态：显示版本、最后心跳、`ONLINE / DEGRADED / OFFLINE`。
- 关联状态：显示`READY / BINDING_REQUIRED / ACTIVATION_REQUIRED / STORE_MISMATCH / MULTIPLE_MATCHES / DISABLED`。
- 异常提示：Agent离线、Channel Agent服务器不可达和operator权限失效使用不同文案；设备告警不伪装为AI或发送失败。

页面可见时每30秒刷新；Store切换后立即重新加载。并发请求使用序列号防止旧Store响应覆盖新Store。一次性绑定码只保存在页面内存，到期或最长10分钟后清除，离开页面时也清除。

## 2. 客服流程

```text
客服登录C
  → C返回真实用户、角色和有效Store
  → Workspace通过C facade读取匹配Agent状态
  → 已激活设备：显示在线/版本/心跳，继续人工AI辅助
  → 未绑定设备：输入精确Agent ID + Device ID申请一次性grant
  → 在客服电脑通过stdin执行Agent enroll
  → Channel Engine管理员独立activate
  → 心跳后Workspace显示READY
```

自助绑定不会注册陌生设备、不会自动激活、不会建立消息发送能力。Agent离线时，现有人工输入、AI建议和人工确认仍可使用；系统不连接PDD、不自动发送。

## 3. 权限与安全

- 浏览器只调用C同源`/api/v1`，不直连Channel Engine，也不持有operator session。
- C按当前Bearer session确定用户，按Store Context确定授权Store；不接受浏览器自报user/store引用。
- 自助grant仅允许`CUSTOMER_SERVICE`，并要求上游存在精确Agent/device、identity为`UNBOUND`、目标Store在授权范围。
- Engine operator session只从Runtime目录内、Git忽略的UTF-8单行引用文件按需读取；内容不进入环境配置、响应、报告或日志。
- 集成默认关闭。远端URL必须HTTPS；只有loopback允许HTTP。上游未配置、不可达、权限失效、协议异常和拒绝均返回非2xx统一Error Envelope。
- 成功登录、grant签发、首次设备观察和状态变化写入0015最小审计；不保存credential、session token、binding code、客户内容或完整上游响应。状态未变不重复写入。

## 4. API、契约和数据变化

新增C接口：

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/v1/workspace/desktop-agent?store_id=...` | `WORKSPACE_ACCESS` + Store scope | 当前客服/店铺匹配设备的最小状态投影 |
| POST | `/api/v1/workspace/desktop-agent/binding-grants` | `CUSTOMER_SERVICE` + Store scope | 为已注册UNBOUND精确设备签发一次性grant |
| GET | `/api/v1/admin/desktop-workflow/audit` | `ADMIN` | 查看最小登录/绑定/状态审计 |

共享contracts升至`0.12.0 / coordinated`，新增`ai-cs.customer-desktop-workflow.v1` schema、compatibility note、changelog和错误码。Gateway Contract V1 wire、A `/api/chat`和Channel Engine API均未修改。

新增迁移`0015_customer_desktop_workflow_v1`，只创建`desktop_workflow_audit_events`。正式Runtime目前仍为`0013_user_management_v1`；标准wrapper会迁移head，因此正式部署前必须先停服、备份并校验SQLite，再协调部署0014/0015、C、B和contracts。

Runtime配置新增：

- `ChannelAgentIntegrationEnabled`：默认`false`。
- `ChannelAgentServerUrl`：loopback HTTP或HTTPS根地址。
- `ChannelAgentOperatorSessionReference`：Runtime目录内secret文件路径，不是secret值。
- `ChannelAgentTimeoutSeconds`：1–60秒。

## 5. 测试结果

| 范围 | 结果 |
| --- | --- |
| C Backend | `145 passed`；覆盖登录审计、Agent状态/变化去重、self-grant、Store/角色隔离、停用设备不跨Store、未配置/不可达/权限异常、secret/URL安全及0015迁移 |
| B Workspace | `36 files / 163 tests passed`；覆盖登录恢复、状态、离线、权限失效、绑定、Store关联和原有客服流程 |
| B typecheck/build | PASS / PASS |
| Admin | `33 files / 84 tests passed`，typecheck/build PASS |
| A保护回归 | `147 passed, 3 skipped`；3项为显式opt-in真实E2E |
| Shared contracts | `15 passed`；25个JSON文件解析通过 |
| Windows | R022 Runtime配置映射PASS；Target Pilot Ready脚本PASS |

完整历史Windows套件中发现两项与R022无关的既有债务：旧`Test-OpsLanMode.ps1`仍要求已被R016架构移除的`/rag-api`代理；`Test-OpsLanRecordFix1.ps1`在独立进程重跑出现一次记录匹配波动（同轮首次执行通过）。本任务未恢复过时代理，也未扩大修改到旧进程记录治理。

Gateway canonical schema SHA-256保持：`fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`。

## 6. 兼容性、部署与剩余风险

- B原三栏Workspace、R020 Product/SKU Resolver、Feedback、A `/api/chat`、R006/R009、RAG、Prompt和模型保持兼容。
- Channel Engine仓库零修改；AI-CS只消费其既有register/heartbeat/status/grant语义。生产协议漂移会fail closed，不做静默容错。
- 正式部署需要：可恢复数据库备份、0014/0015协调迁移、C/B/contracts同批发布、受控HTTPS/loopback Engine地址、Git忽略的operator session引用、Engine预注册和管理员独立激活。
- 当前最大剩余风险是尚无生产Engine凭证/地址和第二台客服电脑真实网络E2E；因此不能宣称生产联通、消息接收或发送已完成。
- Windows旧测试债务应在独立OPS任务中按当前R016网络架构更新，不属于R022功能范围。

## Final Status

`AI_CS_CUSTOMER_DESKTOP_WORKFLOW_READY`
