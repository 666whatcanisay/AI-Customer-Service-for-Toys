# RC5 Final Readiness Report

生成时间：2026-08-13（Asia/Shanghai）

## 一页结论

| Gate | 状态 | 结论 |
|---|---|---|
| `RC5_OFFLINE_STABILITY_READY` | PASS | 离线业务链、AI、策略、安全门、恢复、部署及自动化 UI 均通过 |
| `MORNING_PDD_SCAN_READY` | PASS | 专属 PDD 启动入口的配置、路由、参数和调用链已离线/Mock 验证；今晚未启动 PDD |
| `CURRENT_GREEN_UI_HUMAN_ACCEPTANCE` | NOT_VERIFIED | 必须明早在唯一绿色助手窗口人工点击验收 |
| `RC5_FINAL_READY` | BLOCKED | 仅被上述人工 UI Gate 阻塞 |
| `REAL_PDD_ADAPTER_READY` | NOT_VERIFIED | 明早真实 PDD Gate |
| `REAL_PDD_READ_READY` | NOT_VERIFIED | 依赖 Adapter PASS，需真实页面证据 |
| `REAL_PDD_AI_READY` | NOT_VERIFIED | 需真实消息进入 AI 链 |
| `REAL_PDD_CONFIRM_READY` | NOT_VERIFIED | 需真实会话人工确认证据 |
| `REAL_PDD_SEND_READY` | NOT_VERIFIED | 独立、最后执行 |
| `AI_CS_PRODUCTION_READY` | BLOCKED | 所有真实 PDD Gate 通过前不得宣告生产完成 |

## 本轮问题与修复

| Issue | 原因 | 最小修复 | 验证 |
|---|---|---|---|
| 商品依据显示内部 ID/重复作用域 | 可读 citation 信息在投影丢失且 UI 重复渲染 | 复用现有 citation，内部增加可选 excerpt；UI 去重并以“商品知识”展示 | Backend/Frontend/Engine PASS |
| 无商品上下文仍可做具体商品自动答复 | Decision 未校验 citation 与当前商品/SKU 作用域 | 仅对明确依赖商品事实的 mismatch 阻断 AUTO_LOW_RISK | Engine unit/e2e PASS |
| 停用用户无法重新启用 | 管理界面未连接已有 updateUser 状态能力 | 复用既有 API 增加“启用”动作 | Admin 92 PASS |
| 顶部 AI 状态与状态页不一致 | 两处独立取数与缓存 | 复用同一 Admin store/cache | Admin 92 PASS |
| 进入 PDD 工作台后不能重新识别 | UI 未连接现有只读 inspect/observer 能力 | 增加 loopback、本地鉴权、CSRF/人工意图、single-flight 的薄连接 | Engine/Frontend PASS；真实点击留明早 |
| 30 分钟停止后不能再次开始 | Observer 到期状态没有回到可显式 START 的生命周期 | 保留既有 30 分钟安全限制，修复 `TIMEOUT/STOPPED → START` | Unit/e2e PASS |
| 当前 Host 健康但 Worker 不消费 | 历史 SQLite lock 后 Worker 停滞 | 停止新 Observation、三库一致性备份、原路径重启、投影恢复 | 当前链前8项 PASS；黑盒35/35 PASS |
| 黑盒 Shadow 启动失效 | 数据库身份治理后测试克隆未生成新 ID；脚本仍调用已删除迁移函数；CIM 受页面文件压力影响 | Clone 生成独立 DB identity；普通启动 validate-only；精确 loopback+health fail-closed 识别 | 黑盒35/35、Engine 797 PASS |
| Pilot Governance 可能 fail-open | 原判定只覆盖 Host/Platform 与 Host DB，Buffer、Offline、Spool、源码冻结和 A/RAG 身份未成为必需条件 | 分离 Runtime/Source/Storage/Send/Gate 状态，所有必需依赖 fail-closed；旧派生字段仅兼容解析并忽略 | Governance 18项、Engine Full Gate PASS |
| A/RAG 运行身份缺失 | Platform 有 Activation，但 8420 进程、模型配置、Vector Collection 与冻结源码未纳入身份核验 | 受控启动生成 `AI_CS_RAG` Activation；强校验 PID/启动时间/端口/源码/配置/模型/Vector 路径/Collection/Ready | PowerShell Activation 测试与 Full Gate PASS |

## 架构与安全结论

- 核心路径保持：Provider → Agent → Host → Buffer → CustomerContext → AI-CS → Quality Gate → Reply Strategy → ExecutionPrepared。
- 未修改 Gateway Wire 1.0、ExecutionPreparation 公共协议、ACK/Cursor、Identity 或 Binding 设计。
- 两个本地 POST 动作只允许 loopback assistant session，复用 CSRF/人工意图，single-flight/幂等，失败关闭；不得改变 real read/send 开关。
- `RealExecutionAttempt=0`、`RealSend=0`、`RealReceipt=0`。离线 `ExecutionPrepared` 按测试正常增长。
- Controlled Send 仍被生产 composition 排除；`AUTO_LOW_RISK → 真实发送` 今晚未启用。

## 数据库与恢复

| 数据库 | 实际状态 |
|---|---|
| Platform | `0019_runtime_database_identity_v1`，49 tables，integrity `ok`，Instance `1a915867-4418-44e7-b9b7-4bb098c9b1d9` |
| Host Control | storage `1.0`，45 tables，integrity `ok`，Instance `eacc942b-a1db-4807-810b-9db3e5e3d395` |
| 普通启动 | validate-only；不建库、不自动 migration、不导入测试知识 |
| 一致性备份 | `.runtime/rc5-overnight-closure/host-worker-recovery-backup/manifest.json` |

备份前已停止 Observation 入口与 Host，三库使用 SQLite backup API 并逐一执行 integrity check；Agent binding/config SHA 恢复前后完全一致。

## 最终测试

| 测试 | 结果 |
|---|---|
| Channel Engine / Agent | 797 passed，1 个显式真实 Edge smoke NOT IN SCOPE |
| AI-CS Backend | 153 passed，3 个显式真实本地 E2E NOT IN SCOPE |
| Platform | 181 passed |
| Contracts | 16 passed |
| 绿色助手 | 216 passed + typecheck PASS |
| Admin | 92 passed + typecheck PASS |
| 后端黑盒 | 35/35 PASS |
| Windows 隔离部署 | 13/13 PASS |
| Production Architecture | software RC PASS；真实 Selector BLOCKED |

本轮阶段 Full Gate 证据位于 `.runtime/rc5-governance-freeze/full-gate/`，后端黑盒证据位于 `.runtime/rc5-governance-freeze/backend-blackbox-run/`，Windows 隔离部署报告位于 `.runtime/w/windows-deployment-report.json`，Production Architecture 报告位于 `.runtime/rc5-governance-freeze/production-architecture.json`。当前绿色窗口的人工点击不能由自动化测试替代，因此没有伪写 PASS。

## 冻结与范围

冻结：Provider 抽象、ACK/Cursor、Agent Identity、Device Binding、Gateway、Execution 安全门、MANUAL_CONFIRM、AUTO_LOW_RISK 离线策略、Receipt 隔离。上述能力修改会触发相关全量、黑盒35项、Contracts/消费者与 Architecture Gate 重验。

本轮不阻塞项：代码签名、企业证书、Windows Service、正式 Release Tag。人工编辑后的 Preparation Gate、真实 PDD、通知增强均不在今晚范围；通知不阻塞核心 Pilot。

## 明早唯一人工收口

代码与文档冻结后，先在不启动 PDD Edge 的前提下经受管入口恢复 Host、Platform、A/RAG，生成三份 Runtime Activation 并执行最终 fail-closed Preflight。随后按 `real-pdd/MORNING-PDD-PILOT-RUNBOOK.md`：先确认唯一绿色助手窗口，完成 Synthetic/Replay → 显示 → 人工确认 → Approval → ExecutionPrepared → RealSend=0；通过后将 `RC5_FINAL_READY` 升为 PASS，再由用户手工启动专属 PDD Edge、扫码并进入 Adapter Gate。`may_enter_read_only_pilot=true` 只代表技术预检通过，不能替代该人工授权。
