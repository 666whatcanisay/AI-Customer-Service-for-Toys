# 《AI-CS Channel Engine Operations Console UI Foundation V1 完成报告》

## 1. 结论

Channel Engine Observability Backend 已升级为可直接运行的人机交互控制台。控制台以“当前状态、停留原因、下一步动作、人工处理需求”为首要信息层级，提供 Overview、Workflow Trace、Approval Center、Execution Ledger、Channel Instances、Recovery Center 六个工作区。

本阶段未修改 AI-CS、Gateway Contract 或真实渠道 Transport；所有验收使用 Fake Channel、本地 Mock AI-CS 与临时 SQLite。审批动作只会创建 `PENDING` Execution，不会启动 Worker，不会触发 Adapter/Transport，也不会发送真实消息。

最终状态：`CHANNEL_ENGINE_OPERATIONS_CONSOLE_UI_READY`

## 2. 产品与交互设计

### 2.1 Overview

- 汇总 Runtime、Channel、Browser、Gateway、Storage、Worker、Outbox、Policy 状态。
- 展示 Runtime、已连接渠道、待审批、Execution、UNKNOWN 五项核心指标。
- 根据风险优先级生成单一主结论：`UNKNOWN` > Runtime 异常 > 待审批 > 正常。
- 给出可执行的 Recommended Next Step，并提供最近事件和 Operator Queue。
- 顶部显示数据更新时间与 `SQLite live source`，避免把快照误认为实时流。

### 2.2 Workflow Trace

- 支持使用 message、conversation、request、decision、approval、execution 或 receipt ID 查询。
- 可视化 `Message -> Decision -> Approval -> Execution -> Receipt` 完整链路。
- 每个节点显示状态、标识、停留原因与下一步建议。
- 时间线关联同一 trace 下的结构化事件。

### 2.3 Approval Center

- 明确展示 `Human Approval Required` 与 `AUTO EXECUTION OFF`。
- 按需读取 AI-CS Decision 建议内容，避免将完整客户内容复制进 Observability Event。
- Approve/Reject 均使用确认对话框、操作人、精确确认短语和安全声明。
- Approve 仅调用现有 `ExecutionCoordinator` 创建或返回一个幂等的 `PENDING` Execution。
- Reject 要求原因，不创建 Execution。
- Kill Switch 或执行策略阻断时，服务端拒绝审批转 Execution。

### 2.4 Execution Ledger

- 展示 Execution 状态、Decision、Receipt、Adapter、更新时间和结果摘要。
- 支持状态过滤和标识搜索。
- `UNKNOWN` 使用独立风险颜色，并明确禁止自动重试。

### 2.5 Channel Instances

- 展示 Store、Platform、Instance、Session、Adapter 与 Heartbeat 状态。
- 只显示运行状态和原因码，不展示 credential reference、Cookie、Token 或 Secret。
- 多实例状态独立呈现，单个渠道异常不会被整体健康状态掩盖。

### 2.6 Recovery Center

- 从持久化结构化事件聚合 Recovery 记录。
- 展示 component、attempts、started/completed、reason code 和 next step。
- `UNKNOWN`、`MANUAL_INTERVENTION` 或未完成恢复明确进入人工处理队列。

## 3. Runtime 架构

```text
Browser
  -> Operations Console HTML/CSS/JS
  -> Console API Adapter
  -> /ops/* FastAPI routes
  -> Observability Service
  -> SQLite structured events + existing runtime repositories

Approval UI
  -> explicit confirmation command
  -> OperationsApprovalService
  -> existing ExecutionCoordinator
  -> PENDING Execution only
  -X Worker / Adapter / Transport / real send
```

前端采用无外部依赖的原生 HTML/CSS/JavaScript，并通过同源静态资源端点交付。状态存储、API 调用和各视图渲染被分离；所有服务端动态数据使用 `textContent` 写入 DOM，未使用 `innerHTML`。

## 4. 新增及调整模块

| 模块 | 作用 |
|---|---|
| `observability/ui.py` | 产品化控制台 HTML、CSS、JavaScript 与前端状态管理 |
| `observability/actions.py` | 显式、幂等、无自动执行的人工审批适配器 |
| `observability/models.py` | Recovery 与审批命令/结果模型 |
| `observability/repository.py` | Recovery 事件聚合与人工介入判断 |
| `observability/service.py` | Recovery 查询服务 |
| `observability/api.py` | Console、资源、Recovery 与审批动作 API |
| `app.py` | 将审批服务接入既有 Coordinator，不新增发送边界 |

## 5. API 变化

保留并直接使用已有接口：

- `GET /ops/runtime/status`
- `GET /ops/events`
- `GET /ops/traces/{id}`
- `GET /ops/executions`
- `GET /ops/approvals`
- `GET /ops/console/snapshot`

新增接口：

- `POST /ops/approvals/{decision_id}/approve`
- `POST /ops/approvals/{decision_id}/reject`
- `GET /ops/recoveries`
- `GET /ops/console`
- `GET /ops/assets/operations-console.css`
- `GET /ops/assets/operations-console.js`

审批命令要求：

- `operator`
- 精确 `confirmation_text`：`APPROVE {decision_id}` 或 `REJECT {decision_id}`
- 固定 acknowledgement：`HUMAN_ACTION_REVIEWED_NO_AUTOMATIC_EXECUTION`
- Reject 必须提供 `reason`

审批结果固定声明：

- `automatic_execution_started=false`
- `real_send_triggered=false`

## 6. 安全边界

- 默认不执行；控制台不存在运行 Worker 或真实发送按钮。
- Approval、Execution、Transport 边界保持分离。
- `UNKNOWN` 不自动重试，进入人工核验。
- Kill Switch 与既有执行策略在服务端继续生效。
- Content Security Policy 只允许同源资源；禁止 object、base 重写和 frame 嵌入。
- 响应启用 `no-store`、`nosniff`、`DENY` 与 `no-referrer`。
- UI 不显示 credential reference、Cookie、Token、Password、Secret 或内部技术堆栈。
- 所有视觉验收数据均为本地合成数据。

## 7. 测试与证据

### 7.1 自动测试

- 全量测试：`388 passed`
- 专项控制台测试：`15 passed`
- JavaScript 语法：`node --check` 通过
- `git diff --check`：通过
- 唯一警告：Starlette TestClient 对当前 httpx 适配层的弃用提示，不影响本阶段行为。

覆盖内容：

- 六个页面模块和静态资源渲染。
- Runtime、Channel、Recovery 状态模拟。
- API 集成、响应模型和安全响应头。
- 审批精确确认、幂等、拒绝、Kill Switch 阻断。
- 审批后 Execution 保持 `PENDING`，Fake Executor 调用次数保持 0。
- 结构化 Event、Trace、UNKNOWN、Recovery 和敏感信息扫描。

### 7.2 浏览器视觉验收

- `evidence/operations-console-ui-v1-overview.png`
- `evidence/operations-console-ui-v1-approvals.png`

使用系统 Chrome Headless、本地临时 SQLite 和 Fake Channel 验证 1440x1000 桌面布局。验收确认 Runtime 异常优先于待审批提示、UNHEALTHY 状态使用风险色、审批边界文案可见且无遮挡。

## 8. 运行方式

启动本地服务后访问：

`http://127.0.0.1:18020/ops/console`

控制台面向本机操作。当前不应将其直接暴露到公网。

## 9. 已知风险

- 当前为本地 Operations Console，尚未实现操作员登录、RBAC 或远程访问防护。
- 前端使用 5 秒轮询，不是 SSE/WebSocket 实时事件流；高事件量环境需要分页、增量游标和背压。
- Recovery 记录由现有结构化事件聚合，未来可增加独立 Recovery Ledger 和操作闭环。
- 本阶段只提供审批到 `PENDING` 的边界；执行仍应由独立、受控的 Worker 操作流程触发。
- 已完成桌面浏览器视觉验收；移动/小屏依赖响应式规则，尚未形成多浏览器矩阵。

## 10. 下一阶段建议

1. 在保持本机默认绑定的前提下增加 Operator Authentication 与 RBAC。
2. 引入基于游标的增量事件订阅，避免全量轮询。
3. 为审批与 Recovery 动作增加独立 Audit Event 查询视图。
4. 增加可访问性、键盘操作和跨浏览器视觉回归。
5. 仅在独立安全评审后设计“启动 Execution”操作；不得与审批动作合并。

---

Final Status: `CHANNEL_ENGINE_OPERATIONS_CONSOLE_UI_READY`
