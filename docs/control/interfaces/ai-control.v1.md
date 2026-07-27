# AI 控制面接口 v1

## 1. 目标

本规范冻结 C 运营管理端读取和受控调用 A AI 能力中心的最小控制面。它只用于展示真实运行状态、读取受限元数据，以及由本机管理员显式发起一次无副作用测试或反馈分析。

它不是通用代理、模型管理接口或业务自动化接口。不得据此自动修改 Prompt、发布知识、训练或切换模型、发送客户消息、退款、售后执行、订单/ERP 写入。

版本：`v1`。本文件以 `origin/develop@32feb6108156f5fb4ec297417537d60452d0743f` 的已实现路由为依据；不修改 `contracts/**`。

## 2. 所有者

| 项目 | 结论 |
| --- | --- |
| 数据所有者 | A：模块注册、运行状态、Prompt 元数据、运行指标及分析执行记录 |
| Provider | A，`backend/app/api/routes.py` |
| Consumer | C Admin，`admin_web`，通过 `/ai-api` 同源代理访问 A |
| 传输边界 | Admin 浏览器只访问 C 的 `5174`；Vite 的 `/ai-api/**` 固定代理到服务器本机 `127.0.0.1:8000/**` |
| 认证状态 | 当前测试基线没有正式鉴权；仅限本机 Admin 使用，不能宣称具备生产权限控制 |

## 3. 通用约定

### A 成功 envelope

除特别标注的 HTTP 错误外，A 的成功结果为：

```json
{
  "success": true,
  "message": "ok",
  "data": {}
}
```

**C Consumer 必须从 `data` 读取业务字段。** 例如模块列表实际位于 `data.modules`，不是顶层数组，也不是顶层 `items`。不得因解包失败而展示 Mock 或“0 个模块”。

### C 平台错误

C 的 API 失败使用：

```json
{
  "error": { "code": "STABLE_CODE", "message": "safe message" },
  "request_id": "..."
}
```

不得把请求正文、客户问题、回答、Prompt、密钥或本机绝对路径写入 UI 错误信息。

## 4. API

### 4.1 模块列表（C → A）

`GET /ai-api/api/admin/ai/modules`

返回 `data.modules`：

```json
{
  "success": true,
  "message": "ok",
  "data": {
    "modules": [
      {
        "module_id": "ai_customer_service",
        "name": "AI Customer Service",
        "description": "...",
        "status": "RUNNING",
        "implemented": true
      }
    ]
  }
}
```

`status` 当前允许 `RUNNING`、`PAUSED`、`ERROR`、`PLANNED`。`PLANNED` 不能显示为已运行或具备统计数据。

### 4.2 模块详情和 Prompt 元数据（C → A）

`GET /ai-api/api/admin/ai/modules/{module_id}`

`GET /ai-api/api/admin/ai/modules/{module_id}/prompt`

两者均使用 A success envelope。详情为真实已实现模块返回 `ready`、`model_configured`、`knowledge_count`、`prompt_version`、`prompt_hash` 和进程内指标；计划模块的不可用值必须保持 `NOT_AVAILABLE` 或 `null`。

Prompt 路由只返回 `prompt_version`、`prompt_hash`、安全预览和规则元数据。不得返回完整 Prompt、环境变量或 API key。

### 4.3 显式在线测试（C → A）

`POST /ai-api/api/admin/ai/modules/{module_id}/test`

请求：

```json
{
  "question": "这个款式适合几岁的小朋友？",
  "context": {
    "tenant_id": "TENANT-PDD-SM-TEST",
    "platform": "pdd",
    "store_code": "PDD-SM",
    "product_id": "<已选商品>",
    "sku_id": "<可选 SKU>"
  },
  "include_diagnostics": false
}
```

`question` 必填；`context` 必须完整满足当前冻结的测试数据范围。默认响应仅允许 `answer`、`action`、`risk_level`、`sources`、`latency_ms`、`model`、`request_id`。只有管理员显式勾选 `include_diagnostics=true` 时才可返回受限诊断计数；不得显示原始检索内容。

稳定业务拒绝码：`AI_MODULE_NOT_TESTABLE`（计划模块，409）、`AI_MODULE_NOT_READY`（未就绪，503）。

### 4.4 最新已保存评测（C → A）

`GET /ai-api/api/admin/ai/modules/{module_id}/evaluations/latest`

返回 `data` 中的 `module_id`、`status` 和 `evaluation`。无真实保存评测时为：

```json
{ "module_id": "ai_customer_service", "status": "NOT_AVAILABLE", "evaluation": null }
```

`evaluation.report_path` 仅为受控报告标识，不能作为本机绝对路径或文件浏览能力。

### 4.5 显式反馈分析（C Admin → A → C）

`POST /ai-api/api/admin/ai/feedback-analysis/run`

请求：

```json
{ "maximum": 1 }
```

范围为 `1..100`，默认 `1`。A 只读取 C 的：

`GET /api/v1/admin/ai-quality/badcases`

并只将同一不可变快照的分析证据写回：

`POST /api/v1/admin/ai-quality/analysis-results`

该 A 路由仅允许 loopback 调用。C Admin 的开发代理必须部署在同一服务器本机；不得从 LAN 或公网直接暴露此控制入口。

成功响应的 `data` 为：

```json
{
  "input_feedback_count": 1,
  "analyses": [{
    "feedback_id": "...",
    "revision": 1,
    "feedback_type": "FACT_ERROR",
    "analysis_run_id": "AQR-...",
    "model_version": "qwen3.5:9b",
    "prompt_version": "ai-quality-feedback-v1",
    "writeback_status": "ANALYZED",
    "idempotency_verified": false
  }]
}
```

可处理的稳定 A 错误码：`FEEDBACK_ANALYSIS_EXPORT_UNAVAILABLE` (503)、`FEEDBACK_ANALYSIS_SNAPSHOT_INVALID` (422)、`FEEDBACK_ANALYSIS_MODEL_UNAVAILABLE` (503)、`FEEDBACK_ANALYSIS_OUTPUT_INVALID` (422)、`FEEDBACK_ANALYSIS_WRITEBACK_FAILED` (502)。C 只可展示安全提示和重试建议。

## 5. 状态与幂等

本控制面不拥有业务状态机：

* 模块状态由 A 拥有：`RUNNING` / `PAUSED` / `ERROR` / `PLANNED`。
* 反馈生命周期由 C 拥有：`NEW → ANALYZING → ANALYZED`。
* A 只消费 C 已人工确认且处于 `ANALYZING` 的不可变快照；一次成功回写把 C 记录转为 `ANALYZED`。
* 分析回写以 `analysis_run_id` 幂等：相同 ID、相同反馈证据重放返回同一结果；同 ID 但证据不同或同一 revision 已成功分析均为 409 冲突。
* A 的手动运行请求本身**不**是幂等键；运营人员不得在不理解上次结果前重复点击。C 的回写规则负责阻止重复成功分析。

## 6. 版本与兼容

1. v1 的 A envelope 是兼容承诺；C 适配器必须读取 `data.modules`，不应再尝试把裸数组、`items` 或 UI 占位数据当作 A 模块列表。
2. 任何字段新增必须保持现有字段、列出 Provider/Consumer、更新本文件的版本记录和受影响线路审查；删除/重命名/语义变化必须新建 v2。
3. 此文档不提升共享 `contracts/version.json`。若 A 控制面需要给 B 或外部客户端消费，先走 Interface Owner 冻结、schema、兼容说明及 A/B/C 评审。
4. 当前运行指标是 A 进程内 `since_start` 数据，不是历史报表或人员绩效数据。

## 7. A/B/C 影响范围

| 线路 | 允许责任 | 禁止事项 |
| --- | --- | --- |
| A | 提供真实模块、受限元数据、显式测试和受控 C→A→C 分析 | 不能自动轮询、自动改 Prompt/知识/模型或执行客户业务 |
| C | 通过同源代理解包 A envelope，展示真实状态和受控操作结果 | 不能伪造模块、扩大代理为任意转发，不能绕过 A loopback 保护 |
| B | 不消费本控制面 | 不依赖 Admin 技术状态承担客服流程 |
| OPS | 保持 A `127.0.0.1:8000` 与 Admin `127.0.0.1:5174` 的本机边界，记录版本和受管 PID | 不能暴露 A/Admin 到 LAN 或关闭防火墙 |

## 8. 验收与已知限制

最低验收：A 模块列表真实显示、没有 Mock；A 不可用时 C 只显示受控失败状态；手动测试或反馈分析不改变 Prompt/知识/模型/订单；错误不泄漏敏感正文。

本 v1 不提供正式登录、角色授权、持久审计、生产数据脱敏或外网暴露。它只支持受控内部试运行。

## 9. 变更记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v1 | 2026-07-27 | 首次冻结：根据 A 已实现 envelope、模块状态和反馈分析路径定义 C Admin Consumer 边界；记录 `data.modules` 解包要求。 |
