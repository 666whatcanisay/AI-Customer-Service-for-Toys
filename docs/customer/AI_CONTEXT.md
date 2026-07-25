# B 线 AI 上下文

更新时间：2026-07-25

## 当前任务

- 任务：B-T05-FINAL-INTEROP。
- 分支：`agent/customer-platform-shell-t05`，基线 `origin/develop@36ec2d326d1613f62cb647ad9ef5835315e4db21`。
- 状态：前端实现、测试和 production build 已完成；C-T05 真实建议端点已经兼容 B 冻结 adapter，联调为 `PASS`。

## 允许范围

- `frontend/**`
- `docs/customer/**`

禁止修改 `backend/**`、`platform_backend/**`、`admin_web/**`、`contracts/**`、`extension/**`。

## 工作台入口

- `/`：模块化首页，显示 12 个模块的用途、阶段、输入/输出与人工确认边界。
- `/ai-chat`：保留原三步式 AI 客服完整链路。
- `/suggestions`：提交意见建议。
- `/suggestions/mine`：按本机测试客服 ID 查询建议摘要。
- `/modules/:moduleKey`：未上线模块说明，不提供虚假执行按钮。

布局包含左侧导航、顶部当前客服/店铺、A/C 状态、测试安全横幅和移动端菜单。

## 测试身份与建议

- 本机仅保存 `reporterId`、`reporterName`、`defaultStoreCode`；它不是登录或权限认证。
- 建议正文不写入 localStorage；页面持续提醒不填写客户姓名、电话、地址、订单号或隐私截图。
- 提交：`POST /platform-api/api/v1/customer-suggestions`。
- 我的建议：`GET /platform-api/api/v1/customer-suggestions?reporter_id=`。
- 生产代码不回退 Mock；测试 Mock 只存在于 Vitest。
- 提交响应只适配顶层或 `data` 中的 `suggestion_id/status`；列表严格消费 `{items,total}`。
- 未冻结状态按“状态待确认”显示，不在页面猜测第二套枚举。

## 安全边界

- 当前为测试工作台，仅供内部验证，禁止直接用于真实客户。
- 不自动发送消息，不执行退款、补发、申诉、订单修改或自动化动作。
- 未上线模块只能查看说明并提交建议。
- 本任务没有修改共享 contracts 或其他线路代码。

## 验证

Node：`v24.14.0`。

- `vue-tsc --noEmit`：PASS。
- Vitest：15 个文件、68/68 PASS；包含原 `AiChat` 18 个回归测试。
- `vite build --mode production`：PASS。
- package/lock 无变化；`node_modules`、`dist` 未被跟踪。
- 构建仍报告单个 JavaScript chunk 超过 500 kB，作为后续性能债保留。

## 实际服务检查

- A `GET http://127.0.0.1:8000/api/health`：HTTP 200。
- C `GET http://127.0.0.1:8011/health`：HTTP 200。
- C-T05 `327a765` 在隔离临时 SQLite 服务（`127.0.0.1:8013`）上：POST HTTP 201、非空 `suggestion_id`、`status=SUBMITTED`；GET HTTP 200、`items`、`total=1`。
- 查询项返回与 POST 相同的非空 `suggestion_id` 和 `SUBMITTED`。

因此意见建议真实联调通过；测试使用隔离临时数据，未以 Mock 冒充，服务和数据库已清理。

## 已知风险与交接

- C 建议端点已兼容 `suggestion_id`；当前无 B-T05 交付阻塞。
- production chunk 大于 500 kB；本任务不进行依赖升级或拆包重构。
- 下一任务不得自动实现退款、补发、浏览器扩展、快麦或自动发送。
