# AI-CS V1.0.0

Latest deployment gate: `CANDIDATE_VALIDATED / AI_CS_8423_REPLY_GOVERNANCE_DEPLOYMENT_PENDING`. The repository and current R027 database are both `0023_reply_readiness_v1`; an online backup passed integrity and identity checks before deployment. The long-term Admin entries are `/reply-readiness` and `/knowledge-editor` on port 8423. A, C and Admin must be deployed from the same approved candidate commit. Engine, PDD, auto authorization, Sender and real-send state are outside this gate and remain unchanged. See [8423 Reply Governance Availability V1](docs/control/AI-CS-8423-Reply-Governance-Availability-V1-Report.md).

AI-CS 是面向玩具业务的内部 AI 客服系统。当前权威状态为 `RC5_OFFLINE_STABILITY_READY = PASS`；真实 PDD 的 Adapter、读取、AI、人工确认和发送 Gate 均为 `NOT_VERIFIED`，派生字段 `AI_CS_PRODUCTION_READY=false`。商品风险池 Card 8 的“36题评测 → 补资料 → 新修订 → 复跑”知识闭环已达到`AI_CS_PDD_REPLY_READINESS_KNOWLEDGE_LOOP_READY / SOURCE_ONLY`；完整`AI_CS_AUTOREPLY_READY`仍为FAIL，因为Engine尚未生产Turn Envelope、消费证据包或实现证据绑定的自动策略授权。

当前C数据库源码Head与受控R027 Runtime均为`0023_reply_readiness_v1`；本轮只读核对发现数据库已经完成升级，因此没有重复执行迁移。Card 8不增加数据库结构：C自动聚合最新已审核商品/精确SKU资料并允许一份草稿覆盖，A用真实Router执行完整36题，Admin从逐题缺口跳转既有知识编辑器并携带新修订返回复跑；结果始终不授予发送权。Card 6只读确认Engine现有V1模型会保留开放metadata，却不会消费新证据，也没有`AutoPolicyAuthorizationV2`；最小补救任务见[Card 6验收报告](docs/control/AI-CS-Autoreply-Card6-Functional-Acceptance-Report-V1.md)。Active DB 是 `.runtime/r027-ux-acceptance-data-v1/runtime/platform.sqlite3`；实际绝对路径、DB Identity 和 Migration 必须以 Runtime Activation/状态命令的只读结果为准。普通启动策略为 `VALIDATE_ONLY`，不会执行迁移，也不会自动初始化测试知识；迁移和验收知识初始化必须分别使用受控命令。当前RC5 Gate、已部署版本和启动策略的机器事实源仍位于同级 Channel Engine 仓库的 `docs/production/rc5-final/RC5-Offline-Stability-Version-Matrix.json`。

## Production RC V1（历史基线，不作为当前事实源）

- Release branch：`release/ai-cs-production-rc-v1`
- RC reference：`ai-cs-production-rc-v1`（精确SHA从Git tag解析）
- 产品版本：`AI-CS V1.0.0`
- Repository contracts：`0.13.0 / coordinated`
- Gateway wire：`1.0`，canonical schema保持冻结
- 数据库源码head：`0016_production_hardening_v1`
- 正式Runtime数据库：仍为`0013_user_management_v1`，部署必须先备份并受控迁移
- 部署入口：[Production RC V1 Deployment Checklist](docs/control/AI-CS-Production-RC-V1-Deployment-Checklist.md)
- 冻结证据：[Production Release Candidate Freeze V1](docs/control/AI-CS-Production-Release-Candidate-Freeze-V1.md)

## 正式运行基线（历史 V1.0.0 记录）

- 唯一项目目录：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`
- 发布分支：`release/ai-cs-v1.0.0`
- 功能正式化提交：`9f2b500dc0d6469a04a6953b7886d65e34412a22`
- 正式文案补丁：`9911ba67cef330a7a1b4f03f82de227cbee6982d`
- 防复发测试：`0f230c6f50f8b6162c4e52f3b167053e6592c656`
- 正式稳定标签：`ai-cs-v1.0.0`；精确 SHA 从 Git 与 Runtime 记录解析
- Contracts 源码候选：`0.13.0` coordinated（Gateway wire 仍冻结为 `1.0`）
- 当前受控 Runtime 数据库：`0013_user_management_v1`，完整性 `ok`
- 运行方式：`runtimeMode=standard`；本次 IAM 部署以安全默认 `networkMode=LOCAL` 验收

本地 `origin` 是历史保护仓库，本版本没有声明已经推送到远端或完成远端发布。

## Server RC 基线：R014 Production Server Stabilization

当前分支已将 R011–R013 Server Candidate 固化为 clean Release Candidate `4b6c0bd09de2cca25ae1cb2ca2af76da4455217b`。Gateway wire 保持 `1.0`，repository contracts 为 additive `0.7.0`；Windows `start_ai_cs_server.bat` 已在同一 clean SHA 上完成 Core、Gateway、B、Operations Console 与 C API 的 start/status/Decision/stop 验证。B 客服继续使用 `/api/chat`，未连接生产 Channel Engine/PDD。详见 [`AI-CS Server Release Candidate Stabilization Report V1`](docs/rag/AI-CS-Server-Release-Candidate-Stabilization-Report-V1.md)。

## 四项服务

| 服务 | 目录 | 端口 | 作用 |
| --- | --- | ---: | --- |
| B 客服工作台 | `frontend/` | 5173 | 商品选择、AI 建议、来源与人工确认 |
| C Admin | `admin_web/` | 5174 | 商品、知识、导入、发布与客服启用 |
| A AI 服务 | `backend/` | 8000 | RAG 检索、模型调用与安全回答 |
| C Platform API | `platform_backend/` | 8011 | 业务数据、审核、投影、收据与知识生命周期 |

共享契约位于 `contracts/`，集成测试位于 `tests/`，Windows 运维入口位于 `scripts/windows/`。

## 用户与访问控制

- B 客服工作台和 C Admin 都从 `/api/v1/auth/login` 获取短期 opaque Bearer session，并通过 `/api/v1/auth/me` 恢复服务端身份。
- `CUSTOMER_SERVICE` 拥有 Workspace、AI 建议、Feedback 提交和客服管理权限；首次改密后可绑定多个已启用客服店铺并指定唯一默认店铺，进入Workspace后自动加载且可在授权范围内切换。
- `OPERATOR` 拥有商品、SKU、知识、FAQ、AI 质量、店铺数据和 Feedback 查看权限；`ADMIN` 拥有全部权限。两者都由角色获得全店铺范围。
- 新建和重置账号使用临时口令并强制首次改密；业务 API 在改密前返回 `PASSWORD_CHANGE_REQUIRED`。长期口令不写入代码、命令行、配置或 Git。
- `bootstrap_ai_cs_admin.ps1`保留单管理员入口；`bootstrap_ai_cs_initial_users.ps1`在同一受控 Runtime 配置下检查重复并交互创建批准的三类初始账号，已存在账号只跳过、不覆盖。详细步骤见[`platform_backend/README.md`](platform_backend/README.md)。
- 初始账号已创建且保持 `must_change_password=true`：管理员和运营由角色获得全店范围；客服初始为0条固定绑定，首次使用在改密后进入多店选择流程。部署证据见[Initial Production Accounts Deployment Report V1](docs/control/AI-CS-Initial-Production-Accounts-Deployment-Report-V1.md)。
- R020由C在有效店铺范围内解析会话商品/SKU：唯一候选自动选择，多候选要求人工确认，未知不猜测；B只提交`resolution_id`让C构造既有A chat context，系统仍不自动发送。源码报告见[Store Context Resolver V1 Completion Report](docs/control/AI-CS-Store-Context-Resolver-V1-Completion-Report.md)。
- R021把B三栏页面收敛为生产客服工作流：客服状态为ONLINE/BUSY/OFFLINE，会话状态为NEW/PROCESSING/WAITING_REPLY/COMPLETED；采用、修改、拒绝原因和问题标记进入既有幂等Feedback契约。未接渠道时只提供页面内存的去标识化人工输入，production build不预置验收会话，系统仍不自动发送。报告见[Customer Workspace Production V1 Completion Report](docs/control/AI-CS-Customer-Workspace-Production-V1-Completion-Report.md)。
- R022在Workspace顶部增加当前客服、当前店铺、设备、Agent版本、最后心跳和在线/绑定状态。浏览器只调用C的同源鉴权facade；C按登录用户和授权Store最小投影Channel Agent状态，自助流程只签发已注册未绑定设备的一次性绑定码，独立激活仍由Channel Engine管理员完成。系统不连接PDD、不自动发送，也不修改Channel Engine。报告见[Customer Desktop Workflow Integration V1 Completion Report](docs/control/AI-CS-Customer-Desktop-Workflow-Integration-V1-Completion-Report.md)。
- R023对Backend、Frontend、Admin、Database、API、RAG和Workspace完成只读生产审计，登记22项问题；R024已关闭全部P0/P1源码阻断，R025已形成clean RC。受控正式迁移、TLS/WMI、远端CI与真实外部联通仍必须独立验收。报告见[Code Quality Audit V1 Report](docs/control/AI-CS-Code-Quality-Audit-V1-Report.md)。

## Windows 日常运行

```powershell
cd C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS

.\scripts\windows\start_ai_customer_service.ps1
.\scripts\windows\status_ai_customer_service.ps1
.\scripts\windows\stop_ai_customer_service.ps1
```

启动、停止和状态脚本保持 R008 运行方式，不因 V1.0.0 正式化而改名或改入口。

Gateway Production Server RC 使用独立 wrapper；正式 config 必须显式启用 Gateway，并只引用 Git ignored 的 UTF-8 单行 secret 文件：

```powershell
.\scripts\windows\start_ai_cs_server.bat -NoBrowser -Mode Local
.\scripts\windows\status_ai_cs_server.ps1 -Mode Local
.\scripts\windows\stop_ai_cs_server.ps1
```

## 已验证状态

- 四服务在 5173/5174/8000/8011 以 standard/LOCAL 模式通过 IAM 部署后的启动、健康和身份一致性检查；LAN仍由现有独立网络 Gate 管理。
- 数据库 `integrity_check=ok`，现有商品、知识、发布收据、activation receipt 和迁移历史均保留。
- RAG 活动集合仍为内部物理名 `test_knowledge_v031`，共 56 chunks；该名称不作为用户可见环境标识，也不要求重建向量。
- 模型 `qwen3.5:9b` 为 ready。
- 浏览器验收覆盖 Admin 正式页面、六类模板入口，以及 B 对已发布商品的 3 chunks / 3 citations 回答和人工确认安全边界。

## 安全与数据边界

AI 只生成建议，必须由客服人工确认后发送。系统不自动发送消息、不自动退款、不修改订单。数据库、向量、模型、知识源、日志、运行记录、备份、依赖和客户数据均不得进入 Git。

正式初始化来源使用 `INITIAL_IMPORT`；原始来源、导入批次和审计信息继续保留。测试夹具、回归数据和浏览器证据保留在开发/运行隔离范围，不在运营页面暴露。

## 所有权

- `backend/**`、`docs/rag/**`：A 线
- `frontend/**`、`extension/**`、`docs/customer/**`：B 线
- `platform_backend/**`、`admin_web/**`、`docs/platform/**`：C 线
- `contracts/**`：共享兼容性治理
- `docs/control/**`、`scripts/**`、`tests/**`：Control / OPS / QA

需求状态与交接请从 [Requirement Registry](docs/control/AI-CS-Requirement-Registry-V1.md)、[当前需求摘要](docs/control/AI-CS-Current-Requirement-Status-Summary.md) 和 [交接说明](docs/control/11_交接说明.md) 开始。
