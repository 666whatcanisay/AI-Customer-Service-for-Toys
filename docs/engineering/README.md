# AI-CS Engineering Documentation Baseline

本文档中心记录 AI-CS 当前可运行系统的工程事实，不以历史设计或聊天结论替代代码、运行接口和正式数据库。

## 基线身份

| 项目 | 基线值 |
|---|---|
| Repository | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS` |
| Source branch | `release/product-reliability-hardening-v1` |
| Source SHA | `860d102059cab00ee946512478807f8a8d6efae9` |
| Runtime mode | `standard` |
| Network mode | `LAN` |
| Database revision | `0012_internal_production_finalization_v1` |
| Contracts | `0.5.0`，additive |
| RAG active collection | `test_knowledge_v031`，56 chunks |
| Local model | `qwen3.5:9b`，ready |
| Evidence captured | 2026-08-03，Asia/Shanghai |

## 文档目录

| 文档 | 解决的问题 |
|---|---|
| [01 System Architecture](01_System_Architecture_Baseline_V1.md) | 系统由什么组成，真实调用链和安全边界是什么 |
| [02 Module Responsibility](02_Module_Responsibility_Baseline_V1.md) | A/B/C/Contracts/OPS/QA分别负责什么，不能跨越什么边界 |
| [03 API Current State](03_API_Current_State_V1.md) | 当前运行 OpenAPI、前端实际消费路径和契约现状 |
| [04 Database Current State](04_Database_Current_State_V1.md) | 正式 SQLite、36张业务表、迁移链和关键关系 |
| [05 Runtime Operations](05_Runtime_Operations_Baseline_V1.md) | Windows 启停、身份检查、健康检查、故障处置 |
| [06 Phase 4.1 Acceptance Manual](06_Phase_4_1_Acceptance_Manual_V1.md) | 如何执行 R003 与 R005 的正式业务闭环验收 |
| [Baseline Report](AI-CS_Engineering_Documentation_Baseline_Report_V1.md) | 本次文档建设的证据、检查结果和后续治理入口 |

## 事实来源优先级

发生冲突时按以下顺序判断：

1. 正式 Runtime 受管记录和实时健康接口；
2. 当前 SHA 下的可执行代码、OpenAPI 和 Contracts；
3. 正式 SQLite schema、Alembic revision 与只读健康检查；
4. 本目录工程文档；
5. 历史计划、设计冻结和旧验收报告。

文档中“当前存在”表示已在上述事实来源中核对；“计划”“建议”“待验收”不代表已经实现。

## 关键证据入口

- A 入口：`backend/app/main.py`、`backend/app/api/routes.py`
- B 入口：`frontend/src/main.ts`、`frontend/src/router/index.ts`
- C API 入口：`platform_backend/app/main.py`
- C Admin 入口：`admin_web/src/main.ts`、`admin_web/src/router/index.ts`
- ORM：`platform_backend/app/**/models.py`
- Migration：`platform_backend/migrations/versions/0001_*.py` 至 `0012_*.py`
- Contracts：`contracts/version.json`、`contracts/schemas/**`
- Runtime：`scripts/windows/start_ai_customer_service.ps1`、`status_ai_customer_service.ps1`、`stop_ai_customer_service.ps1`
- 数据健康：`scripts/database-health-check/Invoke-AICustomerDatabaseHealthCheck.ps1`
- 业务 E2E：`tests/e2e/**`

## 维护规则

- API行为变化：先更新 Contracts/OpenAPI，再更新 `03_API_Current_State_V1.md`。
- Migration变化：更新 `04_Database_Current_State_V1.md`，记录新revision、表和回滚边界。
- 启动脚本、端口或运行身份变化：更新 `05_Runtime_Operations_Baseline_V1.md`。
- R003/R005验收步骤变化：只在真实代码或接口已经变化后更新验收手册。
- `.runtime/`、SQLite、Chroma、知识源、模型、日志、浏览器证据和真实数据不得进入 Git。
