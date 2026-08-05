# AI-CS Server Release Candidate Stabilization Report V1

## 1. 结论

AI-CS Server Candidate 已从保护锚点上的 dirty worktree 固化为可复核、Git clean、通过真实 Windows 生命周期验证的 Release Candidate。

Release Candidate 代码 SHA：`4b6c0bd09de2cca25ae1cb2ca2af76da4455217b`。

最终 Gate：`AI_CS_SERVER_RELEASE_CANDIDATE_READY`。

该结论不表示已推送、打 tag、部署生产或连接生产 Channel Engine/PDD。验证结束后四项服务已受管停止。

## 2. 原 dirty 原因

保护锚点 `0b3367f85999f1dc840accf23742c290eb53746b` 之后，R011 Gateway Foundation、T4 Gateway Contract Freeze、R012 Source Baseline 与 R013 Production Server Runtime RC 的改动一直叠加在 worktree，未形成提交。

提交前审计结果：

| 分类 | 文件数 | 内容 |
| --- | ---: | --- |
| Gateway Runtime | 10 | Gateway 实现、A 集成、统一配置与 `.env.example` |
| Production Wrapper / OPS | 7 | common、示例配置、start/status/stop、BAT 与 OPS 测试 |
| Server Console | 4 | typed client、System Status 页面与测试 |
| Contracts | 14 | Gateway/Console schema、版本、changelog、兼容说明、导出器与合同测试 |
| Tests | 3 | Gateway、Contract、Runtime 后端测试 |
| Documentation | 25 | R011–R013 报告、任务卡、状态、交接、台账与 README |
| 合计 | 63 | 全部为文本资产 |

未发现需要延后的独立 Experimental 文件或非生产工具。合同 schema 导出器是 checked-in schema 的可维护生成入口，纳入 RC。Experimental 行为仍按 R012 分类保留，不因此扩大生产职责。

## 3. 精确提交与文件边界

本轮未使用 `git add .`。63 个路径通过显式 manifest 精确暂存，`git diff --cached`、name/status、numstat、binary、secret signature 与 `diff --check` 均完成审计。

排除并确认未提交：

- SQLite/数据库、`.runtime`、Gateway state、PID/runtime record；
- secret、`.env`、credential、日志、evidence；
- `dist`、build、依赖、知识源、向量、模型或客户数据；
- `platform_backend/**`、B frontend/extension、RAG service、Prompt、R006/R009业务源码。

受控提交链：

| 目的 | SHA | 父提交 / Tree |
| --- | --- | --- |
| Server RC source commit | `6ae8d407fc22a8e2a8291fdbfa80706db4ae9f5d` | 父提交 `0b3367f85999f1dc840accf23742c290eb53746b`；tree `6bc8f345fa7e9ff1fcb19e64ebb60cb4a13b4b3e` |
| Windows PowerShell 5.1 compatibility fix | `4b6c0bd09de2cca25ae1cb2ca2af76da4455217b` | 父提交 `6ae8d407fc22a8e2a8291fdbfa80706db4ae9f5d`；tree `248809b3d840c9b8d8e65fd196c9054cb10d71be` |

提交前 index tree 与提交后 commit tree 完全一致。保护锚点未被 reset、rebase 或改写，仍是 RC 提交链祖先。

## 4. Windows Runtime 阻塞修复

真实 Production preflight 首次暴露 Windows PowerShell 5.1 不支持 `[IO.Path]::GetRelativePath`。该调用只影响仓库内、Git ignored secret reference 的安全检查，因此此前临时目录测试没有覆盖。

修复改用已通过 repository-prefix 验证后的 `Substring` 相对路径计算，并新增仓库内 `.runtime` secret reference 回归。修复不改变 HMAC、Gateway routes、Contract schema、secret policy 或业务逻辑。

本机验证凭据由随机数生成，只写入 Git ignored `.runtime`，未回显、未进入命令行、源码、日志、runtime console 或 Git。正式部署仍必须替换为受管 secret 与轮换策略。

## 5. Runtime 身份与生命周期验证

启动入口：`scripts/windows/start_ai_cs_server.bat -NoBrowser -Mode Local -GatewayTimeoutSeconds 180`。

| 验证项 | 结果 |
| --- | --- |
| Git / Runtime identity | branch `release/product-reliability-hardening-v1`；SHA `4b6c0bd09de2`；Source `CLEAN`；四服务身份均“已验证” |
| C API | `RUNNING`，8011，health 200 |
| A Core + Gateway | `RUNNING`，8000，A ready/model configured；Gateway `HEALTHY` |
| B Console | `RUNNING`，5173，HTTP 200 |
| Operations Console | `RUNNING`，5174，页面与 `/ai-api/api/admin/server-runtime` HTTP 200 |
| Server projection | `READY`；version `ai-cs-server-runtime.rc1`；runtime mode `standard` |
| Gateway projection | `HEALTHY`；version `ai-cs-gateway.v1`；Contract `1.0`；`CONFIGURED` |
| Decision | 合成 scope；HTTP 200；`NO_ACTION/HIGH`；`requires_approval=true` |
| Idempotency | 重复请求 `Idempotency-Replayed=true`；decision ID 相同 |
| Stop | Admin → B → A → C 受管停止；8011/8000/5173/5174 全部释放 |

验证只使用合成请求，没有客户数据、生产 Engine 或 PDD。Decision 对不存在的合成商品返回 `NO_ACTION/HIGH`，保持人工审批与无自动执行边界。

## 6. 测试结果

| Gate | 结果 |
| --- | --- |
| A 全量 | `138 passed, 3 skipped`；skip 均为显式 opt-in 真实 C/RAG E2E |
| C R006/R009 定向 | `25 passed`，使用隔离测试数据库 |
| Operations Console | `29 files / 76 tests passed`；typecheck 与 production build PASS |
| Windows OPS | `11/11 suites PASS`；另有 PowerShell 5.1 formal preflight PASS |
| Shared contracts | `7 passed` |
| JSON schema | `17 valid` |
| Gateway Contract freeze | canonical SHA-256 `e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`，未改变 |
| Cached/source gates | 63 路径 manifest、no binary、no sensitive asset、`git diff --check`、tree fingerprint PASS |

测试编排首轮曾因外层循环读取子脚本遗留的 `$LASTEXITCODE`，把已经打印 PASS 的 `Test-OpsT04Fix1.ps1` 误判为失败；改为每个脚本独立 `powershell.exe` 进程后，11 套脚本全部 exit 0。该问题属于验证 harness，不是产品失败。

## 7. 兼容与保护证明

- Gateway Contract V1 的 `/gateway/v1/decisions`、`/gateway/v1/health`、对象、HMAC canonicalization 与 schema hash 未修改。
- `/api/chat`、B 客服语义与人工确认链路未修改。
- R006、R009、`platform_backend/**`、数据库 schema 与业务数据未修改。
- RAG service、Prompt、模型配置语义、知识源、chunks 与 vectors 未修改或重建；运行状态只读观察到活动集合 56 chunks。
- 没有连接生产 Channel Engine、PDD、Browser Execution、Receipt/Event 或自动客户动作。

## 8. 剩余风险

1. RC 提交尚未推送、打 tag、生成签名 artifact 或进入远端评审。
2. 本机随机 secret 只用于 RC 验证；正式部署需要 secret manager、最小 ACL、rotation/revocation 与恢复审计。
3. TLS、reverse proxy、Console access control、rate limit、告警和容量验证仍待部署 Gate。
4. Gateway idempotency 当前为单实例 SQLite；多实例共享状态、加密保留、备份恢复和容量策略仍未完成。
5. 未执行非生产 Channel Engine 跨进程 E2E，也未连接生产 Engine/PDD。
6. 验证结束后服务为停止状态；下一次启动必须继续使用 clean、受审 SHA 和有效的外部 secret reference。

## Final Status

`AI_CS_SERVER_RELEASE_CANDIDATE_READY`
