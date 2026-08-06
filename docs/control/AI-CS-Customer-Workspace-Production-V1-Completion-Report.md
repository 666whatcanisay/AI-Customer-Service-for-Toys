# 《AI-CS Customer Workspace Production V1 Completion Report》

## 结论

- Requirement：`R021`
- Task Gate：`PASS / SOURCE_ONLY`
- Final Status：`AI_CS_CUSTOMER_WORKSPACE_PRODUCTION_READY`
- 本轮只改变B Customer Workspace与项目文档；未新增或修改服务端接口、数据库迁移、共享contract、A/RAG、Gateway、Channel Engine或PDD Adapter。
- 正式Runtime仍为数据库`0013_user_management_v1`。R020的0014尚未部署，因此本报告不声明当前正式Runtime已运行本Workspace Candidate。

## 1. 页面变化

### 三栏生产布局

- 左侧`Conversation Center`：显示客服状态、四态会话队列、状态筛选、未读数和受控人工消息入口。
- 中间`AI Reply Assistant`：显示授权默认店铺、Product/SKU解析、消息时间线、AI草稿、商品/知识依据和人工决策按钮。
- 右侧`Decision Center`：显示人工决策、会话状态、风险等级、知识覆盖、建议动作、行为/问题回执以及显式完成/重新打开操作。

### 状态

- 客服状态：`ONLINE`、`BUSY`、`OFFLINE`。`BUSY`由处理中会话自动推导；离线状态禁止接收人工消息和生成回复。
- 会话状态：`NEW`、`PROCESSING`、`WAITING_REPLY`、`COMPLETED`。
- 采用回复后进入`WAITING_REPLY`；复制不视为已发送。只有客服确认已在外部渠道处理后，才可显式标记`COMPLETED`。
- 已完成会话可重新打开；新客户消息会使旧草稿失效并进入新一轮处理。

### 未接渠道时的输入边界

- Production build不预置验收会话；测试夹具只在Vitest的`test` mode装载，构建产物核对未包含客户A17/B08等fixture文本。
- 未连接PDD或Channel Engine时，可人工新建去标识化会话或向当前会话追加消息。
- 会话内容只保存在当前页面内存，不写入localStorage/sessionStorage。人工输入在进入页面状态前替换常见手机号、邮箱、身份证号和长编号；这只是有限拦截，不构成完整自动脱敏声明。

## 2. 客服流程

```text
登录与服务端RBAC
  -> 自动加载授权默认Store
  -> 打开NEW会话并进入PROCESSING
  -> Conversation Context Resolver识别Product/SKU
  -> 歧义时人工确认，未知时停止生成
  -> AI生成回复、引用、风险和待补充字段
  -> 客服采用 / 修改后采用 / 拒绝 / 标记问题
  -> 采用进入WAITING_REPLY
  -> 客服在外部渠道人工处理后显式COMPLETED
```

- 草稿必须先点击“修改回复”才可编辑，避免无意改写原稿。
- 采用原稿和修改后采用通过既有`AI Interaction Event`记录选择及最终内容。
- 拒绝必须选择问题类型，可填写去标识化原因；系统先保存`REJECTED`行为事件，再通过`interaction_id`保存AI问题反馈。
- “标记问题”不自动作出采用/拒绝决定，客服仍需完成最终人工选择。
- 两类保存均复用稳定幂等键；任何回执无效或请求失败时不显示本地成功。拒绝原因保存失败时草稿继续保持`Waiting Human`，重试复用相同键。
- 系统只提供复制，不自动发送、不退款、不补发、不修改订单。

## 3. 权限

- B路由继续要求服务端身份中的`workspace.access`；无Session进入登录页，首次改密进入改密页，无默认Store的客服进入店铺选择页。
- AI生成按钮要求`ai.reply`，人工选择与问题反馈要求`feedback.submit`。
- `CUSTOMER_SERVICE`的有效Store完全来自C Workspace Context，只能在授权Store处理会话。
- `OPERATOR`的数据查看和`ADMIN`全权限继续由C/Admin既有服务端RBAC承担；本轮没有用前端隐藏替代HTTP 401/403。

## 4. API

本轮没有新增或修改API，repository contracts保持`0.11.0 / coordinated`。B继续严格消费：

- `GET /api/v1/auth/me`
- `GET /api/v1/workspace/context`
- `POST /api/v1/workspace/context-resolutions`
- `POST /api/v1/workspace/ai-replies`，使用`resolution_id`
- `POST /api/v1/ai-interaction-events`，要求`Idempotency-Key`
- `POST /api/v1/ai-response-feedback`，拒绝原因携带既有可选`interaction_id`

Gateway Contract V1 canonical schema SHA-256保持：
`fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`。

## 5. 测试结果

| 范围 | 结果 |
| --- | --- |
| B全量Vitest | `35 files / 157 tests passed` |
| B typecheck | PASS |
| B production build | PASS；保留既有Vite CJS、VueUse注释和大chunk warning |
| C全量 | `135 passed` |
| A全量 | `147 passed, 3 skipped`；跳过均为显式环境变量启用的真实E2E |
| Admin全量 | `33 files / 84 tests passed` |
| Admin typecheck/build | PASS |
| Shared contracts | `12 passed` |
| Production fixture检查 | PASS；构建JS不含validation conversation ID或fixture客户文本 |
| JSON与diff检查 | PASS |

覆盖登录/路由、Store权限、客服三态、会话四态、人工会话、Product/SKU歧义、AI生成、知识引用、直接/修改采用、拒绝原因、问题标记、失败重试幂等、显式完成和反馈权限隔离。

## 6. 风险与后续部署

- 当前人工会话与状态是浏览器会话内工作状态，不是服务端持久化的渠道会话记录；真实渠道会话持久化必须由未来独立Channel Provider任务提供。
- 系统无法验证客服是否真的在外部渠道发送；`COMPLETED`是客服显式确认，不是渠道发送回执。
- 正式部署前必须先按R020交接备份正式SQLite并协调部署0014、C与B；不能只部署新B。
- 不可信网络使用仍需要TLS、受管反向代理、限流与安全审计。
- 前端生产chunk仍超过500 kB，是既有性能风险，不影响本轮功能正确性。

## Final Status

`AI_CS_CUSTOMER_WORKSPACE_PRODUCTION_READY`
