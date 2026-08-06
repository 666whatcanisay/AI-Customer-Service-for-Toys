# 《AI-CS Production Release Candidate Freeze V1》

日期：2026-08-06

任务：R025

结论：`PASS / AI_CS_PRODUCTION_RC_READY`

## 1. Release版本

| 项目 | 冻结值 |
|---|---|
| 产品版本 | `AI-CS V1.0.0`（本任务不改变业务版本语义） |
| RC引用 | `ai-cs-production-rc-v1`（本地annotated tag，精确SHA由Git解析） |
| Release branch | `release/ai-cs-production-rc-v1` |
| 起始父提交 | `bd6e10c4cb084a4b804ec37432a93b293b3c1c08` |
| Repository contracts | `0.13.0 / coordinated` |
| Gateway wire | `1.0` |
| 数据库源码head | `0016_production_hardening_v1` |
| 正式Runtime数据库 | `0013_user_management_v1`（本冻结任务未迁移） |

RC包含R020 Store Context、R021 Customer Workspace、R022 Customer Desktop Workflow、R023 Code Audit与R024 Production Hardening的协调源码。它不包含真实PDD、生产Channel Engine连接、自动发送、Prompt/模型或R006/R009业务变更。

## 2. Git状态与Source Freeze

- 开始状态：110个tracked diff文件、58个untracked文件，基于上述父提交；所有文件逐项归类为A、B、C、Admin、OPS、contracts、tests或docs生产候选。
- 暂存规则：通过显式文件manifest传给`git add -- <path...>`；禁止并未使用`git add .`。
- 提交前检查：`git diff --cached --name-status`、`--stat`、`--check`、禁止资产扫描、secret模式扫描、Gateway/RAG指纹与外部Channel Engine状态。
- 冻结状态：Release branch、单一受控commit与annotated RC tag形成后，tracked/untracked工作树必须为0；精确commit SHA以`git rev-list -n 1 ai-cs-production-rc-v1`解析并在最终交接输出。
- 未纳入：`.runtime`、`.env`、SQLite/DB、向量、知识源、模型、日志、evidence、备份、依赖、`dist`及其他build产物。

## 3. Migration状态

迁移链为单一线性head：

```text
0013_user_management_v1
  → 0014_store_context_resolver_v1
  → 0015_customer_desktop_workflow_v1
  → 0016_production_hardening_v1 (head)
```

验证结果：

- Alembic `heads`只返回0016。
- 0014隔离升级/降级保留IAM与商品目录表。
- 0015隔离升级/降级保留IAM与Store Context表。
- 0016完成`0013 → head → 0013 → head`，验证登录失败bucket、发布租约字段与唯一默认Store索引。
- 三个migration专项测试全部通过；正式数据库hash在验证前后相同。
- 正式数据库最终为0013、`integrity_check=ok`、0 foreign-key violation，SHA-256为`EA7C002D9C968C6D8A291FBBF087599B84602EFA8BA13A0192BE6E9327CD7C57`。

## 4. 测试结果

| Gate | 结果 |
|---|---|
| A Backend | `150 passed, 3 skipped`；3项为显式opt-in真实外部E2E |
| C Backend / migration | `155 passed`；0014–0016专项3项通过 |
| B Frontend | `36 files / 164 passed`；typecheck、production build通过 |
| Admin | `34 files / 85 passed`；typecheck、production build通过 |
| Contracts | `15 passed`；20个JSON Schema有效 |
| Security专项 | A 24项；C内部身份/Desktop权限/日志/IAM专项通过 |
| Production Web | 3项通过 |
| Windows Runtime | `16/16`套件通过 |
| Dependency | A/C `pip check`通过；B `npm audit`、Admin `pnpm audit`均为0 known vulnerability |
| CI配置 | 6个Workflow YAML解析通过 |
| Source | `git diff --check`通过；候选无禁止资产 |

## 5. Security与Contract保护

- 候选扫描未发现私钥、AWS访问键、GitHub/OpenAI token或批准初始化口令。通用credential模式命中仅来自已核对的合成测试fixture/test control，不是生产凭据。
- 内部服务凭据、Gateway HMAC secret和TLS key均只允许使用Git ignored Runtime文件引用；禁止inline、命令行、日志、浏览器或报告输出。
- Gateway canonical schema SHA-256保持`fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`，Gateway contract实现无diff。
- RAG向量库保持188416 bytes，SHA-256为`0c6ca2e39618dd81ad764e7063ec787cc441316415a3d857de86d4b47fb41417`；未执行sync、clear、rebuild、re-slice或re-embedding。
- 外部Channel Engine仓库HEAD保持`673ce7e1e89cca977463e2e98cec8d00055a6e98`；本任务未向该目录写入。PDD Adapter与自动发送边界无diff。

## 6. 部署要求

受控主机最低环境：

- Windows与PowerShell 5.1；Git；A Python 3.11.9兼容环境；C Python 3.12.13兼容环境；Node.js 22.23.1、npm 10.9.8、pnpm 11.18.0或经CI验证的等价版本。
- 发布引用必须解析到`ai-cs-production-rc-v1`且工作树clean；禁止从dirty目录启动。
- A/C内部服务凭据与Gateway secret必须独立，使用受限ACL文件；LAN还必须提供受信TLS certificate/key引用和精确Private网络防火墙规则。
- 部署前停止四服务，验证8000/8011/5173/5174无监听，对正式SQLite做可恢复备份、hash、revision、integrity与逐表行数记录。
- 以同一RC SHA顺序执行0014–0016迁移、B/Admin build、start/status/health；完成登录、退出、RBAC、Store Context、AI Reply非自动发送、Gateway签名Health/Decision（仅启用时）与stop验证。

精确步骤与逐项签收见[Production RC V1 Deployment Checklist](AI-CS-Production-RC-V1-Deployment-Checklist.md)。

## 7. 恢复方案

1. 停止所有受管服务并确认端口释放；保留失败数据库、日志和运行记录作为受限审计资产。
2. 优先恢复部署前SQLite备份；如果使用Alembic逻辑回滚，只允许在已验证副本上先演练`0016 → 0013`。
3. 数据库回到0013时，源码必须同步回到兼容的pre-R020引用；不得让0016源码长期运行0013数据库。
4. 核对恢复数据库hash、revision、integrity、foreign keys与关键表行数，再从匹配SHA启动。
5. RAG向量/知识未被本RC迁移；不得以回滚为由清空、覆盖或重建RAG。

## 8. 剩余风险

1. 正式数据库仍为0013，0014–0016只完成隔离验证；正式迁移需要独立Deployment Gate、备份与回滚窗口。
2. LAN TLS证书、信任分发、轮换及精确防火墙规则属于部署输入；缺失时LAN必须fail closed。
3. 当前主机WMI/CIM进程元数据提供程序曾超时；Runtime会安全拒绝无法验证的status/stop。正式部署前必须恢复并验证WMI健康。
4. 远端GitHub Actions尚未运行；本报告只声明本地等价Gate通过。本地`origin`不能被当作远端发布证明。
5. 真实PDD、生产Channel Engine、第二台客服电脑与真实模型/RAG业务E2E未执行，仍需独立验收。
6. B生产bundle仍有大于500 kB警告；sessionStorage Bearer依赖TLS/CSP/XSS防护；N+1/分页、HTTP连接池与deprecation warning保留为P2维护项。

## Final Status

`AI_CS_PRODUCTION_RC_READY`
