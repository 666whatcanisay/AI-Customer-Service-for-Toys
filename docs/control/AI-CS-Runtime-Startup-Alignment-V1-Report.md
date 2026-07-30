# AI-CS Runtime Startup Alignment V1 Report

> 日期：2026-07-30  
> 需求：R008 Runtime Startup Alignment V1  
> Target：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`  
> 最终分支：`control/r008-runtime-startup-alignment-v1`  
> 最终运行 SHA：`dd379278837a4f816dfb626292a26b0c54cce0cc`  
> 结果：`RUNTIME_STARTUP_ALIGNMENT_COMPLETE`

## 1. 问题与根因

标准启动脚本原先没有把 Target 的正式知识/向量路径和活动集合作为明确运行配置传给 A，并以 `documents` 的 chunks 作为知识 smoke 判断。实际 Chroma 数据为：

| Collection | Chunks |
| --- | ---: |
| `documents` | 0 |
| `test_knowledge_v031` | 47 |

因此 `documents=0` 被错误解释为整个 RAG 无知识；同时调用者环境变量不同还可能令 A 回退到 `backend/vector_db`，产生运行路径漂移。

## 2. 实施结果

1. A 增加 `ACTIVE_COLLECTION_NAME`，默认继承现有 `TEST_KNOWLEDGE_COLLECTION_NAME`；运行脚本显式配置主集合与活动集合，不再把 `documents` 写死为启动判断。
2. `GET /api/knowledge/statistics` 兼容保留总 chunks，并返回 `primary_collection_name`、`active_collection_name`、活动 chunks、可用性和 Chroma 实际可见集合列表。
3. 标准启动显式传递 Target 知识、向量、日志和 C 资料路径；A health、`ready=true`、`model_configured=true` 仍为硬 Gate。
4. 知识同步失败、活动集合缺失或空集合只输出 warning，四服务继续启动；活动集合非空时继续执行真实 AI chat smoke。
5. status 同时显示 active collection、active chunks、available collections 和总 chunks。
6. `start_target_pilot.ps1` 改为调用 `start_ai_customer_service.ps1` 并使用 Local readiness，不再误调 LAN 启动入口。
7. 启动失败时按 `Admin → B → A → C` 清理本轮服务。真实复验暴露“HTTP 已健康但 listener PID 尚未写入记录”的窗口后，补充了清理前受控监听身份回填和清理后记录/端口双校验；没有按端口强杀。

## 3. Commit 清单

| Commit | 内容 |
| --- | --- |
| `acfdc1a92da652a7ea795b5e497eba5d997f5891` | 活动集合配置、A 统计投影、启动/status/Target Pilot 对齐及测试 |
| `9df6616625e8f0467f86b1cceb0b937402a367a4` | A 线状态、变更、交接和 machine-context |
| `6070ad1a7124346ca8b859c7b655ea8737b89545` | 关闭部分启动清理的 listener-record 竞态 |
| `dd379278837a4f816dfb626292a26b0c54cce0cc` | 记录竞态关闭并形成最终运行 HEAD |

## 4. 测试结果

- A Backend：`101 passed, 3 skipped`；3 项均为需显式环境变量的真实 E2E，非失败。
- Windows OPS：8 个 `Test-*.ps1` 测试套件全部通过。
- PowerShell 静态解析与 `git diff --check`：通过。
- contracts：未修改，仍为 `0.2.0`。
- requirements、lockfile、UI、数据库结构、Prompt、模型：未修改。

## 5. 最终 stop → start → status 验收

使用同一配置：`.runtime/phase-e/config/green-standard.local.ps1`。

| 服务 | 端口 | 受管 PID | 监听 PID | 状态 |
| --- | ---: | ---: | ---: | --- |
| C API | 8011 | 19188 | 636 | `RUNNING` / health 可用 |
| A | 8000 | 21840 | 24188 | `RUNNING` / ready / model configured |
| B | 5173 | 17516 | 17516 | `RUNNING` / 页面可用 |
| C Admin | 5174 | 25720 | 20820 | `RUNNING` / 页面可用 |

四个运行记录均验证为 Target `dd37927...`、源码 `CLEAN`。C revision 为 `0008_customer_feedback_loop_v1`。

RAG 状态：

- active collection：`test_knowledge_v031`
- active chunks：`47`
- available collections：`documents=0`、`test_knowledge_v031=47`
- total chunks：`47`

代理验证：Admin→A、Admin→C、B→A、B→C 均为 HTTP 200。真实 `qwen3.5:9b` smoke 返回 `CONTROLLED_ANSWER`、3 条来源，并保留 `SUGGESTION_ONLY`、`AUTO_SEND_DISABLED`。

## 6. 数据与安全边界

- 正式 SQLite 仍为 `.runtime/phase-e/data/standard-platform.sqlite3`，未重建、未清空、未迁移结构。
- 正式向量路径仍为 `.runtime/phase-e/standard-rag/vector-db`，未删除任何 collection 或向量数据。
- Recovery `AI-CS-pilot-baseline-recovery-v1@cbc77ed...` 保持停止、完整、仅回滚使用。
- 未修改业务回答逻辑、UI、contracts、R006、数据库结构、Prompt 或模型。
- 知识 warning 只表示服务降级可启动，不代表 AI smoke 或 Pilot 业务验收通过。

## 7. 日常命令

```powershell
scripts/windows/stop_ai_customer_service.ps1 -ConfigPath .runtime/phase-e/config/green-standard.local.ps1
scripts/windows/start_ai_customer_service.ps1 -ConfigPath .runtime/phase-e/config/green-standard.local.ps1
scripts/windows/status_ai_customer_service.ps1 -ConfigPath .runtime/phase-e/config/green-standard.local.ps1
```

最终状态：`RUNTIME_STARTUP_ALIGNMENT_COMPLETE`
