# AI-CS RC5 开发导航图

本文件是后续 Codex、测试人员和接手程序员的第一入口。开始修改前先定位 Owner Module，遵循 `Change → Test` 最小回归；不要重新扫描两个仓库，也不要无理由改动冻结模块。

## 仓库与运行边界

| 领域 | 仓库 | Owner / Entry Point | 主要文件 | Contract / Tests | Do Not Touch |
|---|---|---|---|---|---|
| PDD 页面只读 | Channel Engine | `channel_agent` / `pdd_page_port.py` | `pdd_readonly_driver.py`、`edge_pdd_observe.py`、`pdd_observer.py` | PDD Snapshot/Observation；`test_real_pdd_adapter_foundation_v1.py` | 不猜 Selector，不自动登录，不读私有接口 |
| Agent 本地控制与绿色助手桥 | Channel Engine | `channel_agent.desktop` | `desktop.py`、`windows.py`、`windows_app.py` | Local Assistant API；desktop/windows tests | 不绕过 loopback session、CSRF、人工意图和安全开关 |
| Spool / Cursor / ACK | Channel Engine | `channel_agent.observation_runtime` | `edge_spool.py`、`observation_runtime.py` | Agent Control 2.1；provider/ACK tests | 已冻结；禁止无理由重构 |
| Host Observation Worker | Channel Engine | `channel_engine.agent` | `observation_worker.py`、`assistant_factory.py` | Agent Control 2.1；worker/e2e tests | ACK 后才推进 Cursor |
| Buffer / 多轮上下文 | Channel Engine | `channel_engine.customer_assistant` | `buffer.py`、`runtime.py`、`context.py` | internal context model；offline blackbox | 不跨店、客户、会话混用历史 |
| Decision / Quality / 策略 | Channel Engine | `customer_assistant` | `models.py`、`offline_control.py` | Reply Decision internal model | 商品作用域不一致必须 fail-closed |
| Execution 安全门 | Channel Engine | `channel_engine.execution` | execution/authorization/receipt modules | Execution contract | 不绕过 Approval、授权、店铺和会话校验 |
| AI-CS Gateway / RAG | AI-CS | `backend/app/gateway` | `service.py`、`contract.py` | Gateway Wire 1.0 / canonical SHA | 不为 UI 修复修改公共 wire |
| Platform 工作区 API | AI-CS | `platform_backend/app` | workspace、agent integration、user modules | Platform REST | 普通启动只校验数据库，不自动迁移 |
| 绿色客服助手 | AI-CS | `frontend` | `ChannelAgentDesktopLayout.vue`、`ReplyAssistantPanel.vue`、`channelMessageAdapter.ts` | local assistant + platform API | 不把 ExecutionPrepared 显示为已真实发送 |
| Admin | AI-CS | `admin_web` | `App.vue`、`AiCapabilityCenterView.vue`、`UserManagementView.vue` | Platform Admin API | Header/状态页共用同一状态事实源 |
| Windows 包 | Channel Engine | `packaging/windows-client-v2` | composition、build/install scripts | release manifest | Controlled Send、测试旁路不得进入正式包 |

## 固定验证制度

项目只使用两种验证模式，不再为每个小改动重复做完整收口：

| 模式 | 用途 | 最低要求 | 禁止事项 |
|---|---|---|---|
| Change Gate | 日常功能开发 | Reuse First、Owner 模块定向测试、相关安全 Smoke | 不跑无关全量、不生成 BOM、不重写最终报告 |
| Full Gate | 一批功能完成并准备进入下一个 Gate | 停止新增功能后，一次性执行受影响全量、黑盒、架构、包、安全、BOM 和文档冻结 | 不顺手修 P2/P3，不在同一阶段反复封版 |

固定节奏：`一批功能开发 → 各项 Change Gate → 开发截止 → 一次 Full Gate → BOM/文档 → Freeze`。公共 Contract、数据库 Migration、Execution 安全门或生产 Composition 发生变化时，Change Gate 必须扩大到所有直接消费者与对应安全 Gate。

| Change | 最低测试 |
|---|---|
| PDD Adapter / Observer | Adapter、Observation、Replay、Cursor/ACK、Selector fail-closed |
| Buffer / Context / Decision | Engine 对应单元、offline e2e、黑盒35项 |
| Gateway / AI-CS Backend | Backend 全量、Contracts、Engine Gateway consumer tests |
| 绿色助手 | Frontend 全量 + typecheck + UI/Decision/Preparation 一致性 |
| Admin | Admin 全量 + typecheck |
| Windows 包/Composition | allowlist、manifest/SHA、隔离安装13项、Production Architecture Gate |

统一入口以仓库现有脚本为准；若命令漂移，先更新本图，不新造平行脚本。真实 PDD Replay 必须走：采集 → 脱敏 → 扫描 → 不可变 Fixture SHA → 审批 Sidecar → Approval Registry 锚点 → Replay。未经审批不得导出或长期保留。

当前阶段冻结后进入真实 PDD READ 开发期：Selector、Observer、商品、SKU、角色等单项修改只跑 Change Gate；整批读取能力完成后只做一次 Full Gate。

## 冻结能力

Provider 抽象、ACK/Cursor、Agent Identity、Device Binding、Gateway Wire 1.0、Execution 安全门、Synthetic/Real Receipt 隔离均已验证并冻结。修改这些模块会触发完整消费者回归、黑盒35项与 Production Architecture Gate。
