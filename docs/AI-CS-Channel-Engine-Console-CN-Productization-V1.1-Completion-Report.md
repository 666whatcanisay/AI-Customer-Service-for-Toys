# 《AI-CS Channel Engine Console 中文产品化升级 V1.1 完成报告》

## 1. 完成结论

Operations Console 已从英文工程监控界面升级为面向中国电商客服与运营团队的“AI 智能客服运营执行控制中心”。

本次升级完成全中文导航、业务状态表达、六步会话追踪、客服审核工作台、执行审计、店铺渠道状态以及问题诊断与恢复。Approval、Execution、Worker 和 Transport 的原有安全边界没有改变；批准只创建一条“待执行”任务，不会自动运行，也不会发送真实消息。

Final Status：`CHANNEL_ENGINE_CONSOLE_CN_READY`

## 2. 产品定位

控制台的主要用户从开发/运维人员扩展为：

- 客服人员：查看客户问题、核对 AI 建议并进行人工批准或拒绝。
- 客服主管：查看待办、执行结果、结果待确认任务和风险边界。
- 运营人员：查看店铺渠道状态、业务流程停留原因与建议下一步。
- 技术支持：在问题诊断与恢复中查看系统组件和有限恢复记录。

信息层级调整为：

1. 现在是否可以安全运行。
2. 是否有客服需要立即处理的会话。
3. 一条消息进行到了哪一步。
4. 为什么停留。
5. 下一步应该由谁做什么。

## 3. 页面升级

### 3.1 运行总览

- 展示系统运行、店铺渠道、待人工审核、执行记录和结果待确认数量。
- 主状态按照“结果待确认 > 系统异常 > 待人工审核 > 正常”排序。
- 将 Runtime、Browser、Gateway、Worker 等工程组件转换为“系统运行、浏览器、AI 服务、执行程序”等业务名称。
- 提供客服待办、最近业务事件、异常原因和建议下一步。
- 显示数据更新时间与“本地数据实时读取”。

### 3.2 会话流程追踪

业务流程统一展示为：

```text
客户消息
  ↓
AI 分析
  ↓
回复建议
  ↓
人工确认
  ↓
受控执行
  ↓
结果凭证
```

- 可使用消息、会话、AI 请求、决策、审核、执行或凭证编号查询。
- 默认打开最近一条业务流程，减少客服手工复制编号。
- 展示当前步骤、停留原因、安全的下一步和关联业务编号。
- Event Type 全部转换为中文业务事件。

### 3.3 人工审核中心

审核详情新增并明确展示：

- 客户问题。
- AI 建议。
- 知识来源。
- 风险等级。
- 下一步操作。

Gateway Contract V1 当前没有在 Decision 中持久化知识引用和风险等级。控制台不伪造信息：

- `knowledge_sources=[]` 时显示“当前 AI 响应未提供可核验的知识来源”。
- `risk_level=UNSPECIFIED` 时显示“未标注（按需人工复核）”。
- 缺失信息不会解除人工审核要求。

客户问题和 AI 建议通过只读审核详情接口按需读取，不复制到 Observability Event。

审核动作采用中文精确确认短语：

- `批准 {decision_id}`
- `拒绝 {decision_id}`

原英文确认短语作为后端兼容输入保留，不在中文 UI 中展示。

### 3.4 执行审计记录

- 原 Execution Ledger 改为“执行审计记录”。
- PENDING、RUNNING、SUCCESS、FAILED、UNKNOWN 分别展示为“待执行、执行中、已成功、已失败、结果待确认”。
- 每条记录展示决策/审核编号、尝试次数、结果凭证、时间和下一步。
- “结果待确认”始终提示禁止自动重试并要求人工核对渠道侧结果。

### 3.5 店铺与渠道

- 原 Channel Instances 改为“店铺与渠道”。
- 展示店铺、渠道、登录会话、适配器、平台连接和最近心跳。
- 不展示 Credential Reference、Cookie、Token、Password 或 Secret。
- 模拟环境明确显示“模拟隔离运行”和“真实平台访问保持关闭”。

### 3.6 问题诊断与恢复

- 原 Recovery Center 改为“问题诊断与恢复”。
- 展示问题组件、业务化原因、恢复次数、当前状态和人工处理建议。
- 强调有限恢复、禁止无限重试和默认安全阻断。

## 4. 中文状态体系

新增统一前端状态词典，底层协议值保持不变，界面统一使用业务语言：

| 底层状态 | 中文业务状态 |
|---|---|
| `HEALTHY` | 正常 |
| `UNHEALTHY` | 异常 |
| `RUNNING` | 运行中 |
| `WAITING_APPROVAL` | 待人工审核 |
| `PENDING` | 待执行 |
| `SUCCESS` | 已成功 |
| `FAILED` | 已失败 |
| `UNKNOWN` | 结果待确认 |
| `RECOVERING` | 恢复中 |
| `RECOVERED` | 已恢复 |
| `MANUAL_INTERVENTION` | 需要人工介入 |

未知 Reason Code 不直接暴露给客服，而是显示“请在问题诊断中查看详细原因”。已知原因码转换为可执行的中文说明。

## 5. 新增只读审核详情 API

新增：

`GET /ops/approvals/{decision_id}/review`

返回：

- `customer_question`
- `ai_suggestion`
- `knowledge_sources`
- `knowledge_source_status`
- `risk_level`
- `risk_basis`
- `next_step`
- Decision、Conversation、Message 与 Gateway 关联信息

该接口只读取现有 Message 与 Decision，不修改 AI-CS、Gateway Contract 或执行链。

## 6. 安全边界

- 未经人工审核不能创建 Execution。
- 批准后只创建或幂等返回一条 `PENDING` Execution。
- 控制台不启动 Worker。
- 控制台不调用 Adapter 或 Transport。
- 控制台不发送渠道消息。
- Reject 不创建 Execution。
- Kill Switch 继续在服务端阻断批准转执行。
- UNKNOWN 禁止自动重试。
- 客户问题不写入结构化 Observability Event。
- 前端继续使用 `textContent` 渲染动态内容，不使用 `innerHTML`。

## 7. 测试结果

### 自动测试

- 全量测试：`388 passed`
- 中文控制台专项测试：`15 passed`
- JavaScript 语法检查：通过
- CSP、安全响应头和 DOM 安全测试：通过
- 中文状态映射测试：通过
- 六步会话流程测试：通过
- 审核详情数据与事件脱敏测试：通过
- 中文确认短语、幂等、拒绝和 Kill Switch 测试：通过

第一次全量运行中，一个既有 Runtime Recovery 用例出现旧健康快照的瞬时时序失败；该用例独立复跑通过，随后全量复跑 `388 passed`。本次未修改 Runtime Recovery 逻辑。

唯一持续警告为 Starlette TestClient 与当前 httpx 适配层的弃用提示，不影响本次功能。

### 浏览器视觉验收

使用本地 Fake Channel、Mock AI-CS、临时 SQLite 与系统 Chrome Headless 完成 1440×1100 验收：

- `evidence/operations-console-cn-v1.1-overview.png`
- `evidence/operations-console-cn-v1.1-approvals.png`
- `evidence/operations-console-cn-v1.1-trace.png`

验收确认：中文字体与布局正常、状态无英文协议值泄漏、审核信息完整、六步流程可视、知识/风险缺口明确、自动执行关闭提示始终可见。

## 8. 运行入口

本地服务启动后访问：

`http://127.0.0.1:18020/ops/console`

当前控制台仍定位为本机运行界面，不应直接暴露到公网。

## 9. 已知限制

- Gateway Contract V1 未持久化知识引用与风险等级，因此当前只能如实展示“未提供/未标注”。
- 客户问题属于业务敏感内容；在增加 Operator Authentication 与 RBAC 前，控制台必须仅限本机访问。
- 控制台仍使用 5 秒轮询，尚未使用增量事件订阅。
- 本阶段不提供“启动执行”按钮；执行必须继续由独立受控流程处理。

## 10. 下一阶段建议

1. 在不修改 Gateway Contract V1 的前提下设计独立、版本化的审核证据扩展模型，持久化 citations 与风险评估来源。
2. 增加操作员登录、角色权限和审核审计查询。
3. 增加按店铺、班次和风险等级的客服待办筛选。
4. 增加会话摘要、审核 SLA 与结果待确认处理闭环。
5. 建立中文可访问性和多浏览器视觉回归矩阵。

---

Final Status: `CHANNEL_ENGINE_CONSOLE_CN_READY`
