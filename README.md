# AI-CS V1.0.0

AI-CS 是面向玩具业务的内部 AI 客服系统。当前版本已完成 R008 运行收敛、R009 商品知识导入、R006 客服目录激活、R006.1 AI 知识发布、R006.2 客服体验优化、R016 用户身份/RBAC/店铺绑定、R018 内部账号策略以及 R019 Production IAM 部署。正式数据库已迁移到0013，三个批准的初始账号已经创建并通过真实登录、首次改密、RBAC和店铺范围验收，当前 Gate 为 `AI_CS_INITIAL_ACCOUNTS_READY`。

## 正式运行基线

- 唯一项目目录：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`
- 发布分支：`release/ai-cs-v1.0.0`
- 功能正式化提交：`9f2b500dc0d6469a04a6953b7886d65e34412a22`
- 正式文案补丁：`9911ba67cef330a7a1b4f03f82de227cbee6982d`
- 防复发测试：`0f230c6f50f8b6162c4e52f3b167053e6592c656`
- 正式稳定标签：`ai-cs-v1.0.0`；精确 SHA 从 Git 与 Runtime 记录解析
- Contracts 源码候选：`0.10.0` coordinated（Gateway wire 仍冻结为 `1.0`）
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
- `CUSTOMER_SERVICE` 拥有 Workspace、AI 建议、Feedback 提交和客服管理权限；首次改密后可选择并绑定一个或多个已启用客服店铺，不再要求固定默认店铺。
- `OPERATOR` 拥有商品、SKU、知识、FAQ、AI 质量、店铺数据和 Feedback 查看权限；`ADMIN` 拥有全部权限。两者都由角色获得全店铺范围。
- 新建和重置账号使用临时口令并强制首次改密；业务 API 在改密前返回 `PASSWORD_CHANGE_REQUIRED`。长期口令不写入代码、命令行、配置或 Git。
- `bootstrap_ai_cs_admin.ps1`保留单管理员入口；`bootstrap_ai_cs_initial_users.ps1`在同一受控 Runtime 配置下检查重复并交互创建批准的三类初始账号，已存在账号只跳过、不覆盖。详细步骤见[`platform_backend/README.md`](platform_backend/README.md)。
- 初始账号已创建且保持 `must_change_password=true`：管理员和运营由角色获得全店范围；客服初始为0条固定绑定，首次使用在改密后进入多店选择流程。部署证据见[Initial Production Accounts Deployment Report V1](docs/control/AI-CS-Initial-Production-Accounts-Deployment-Report-V1.md)。

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
