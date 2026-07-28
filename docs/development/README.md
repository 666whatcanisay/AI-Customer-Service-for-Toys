# 工程协作规范

## 代码所有权

| 线路 | 可修改范围 | 核心职责 |
| --- | --- | --- |
| A | `backend/**`、`docs/rag/**` | RAG、模型调用、评测和 AI 控制只读投影 |
| B | `frontend/**`、`extension/**`、`docs/customer/**` | 客服工作台与客服端 API 消费 |
| C | `platform_backend/**`、`admin_web/**`、`docs/platform/**` | 业务资料、运营后台、审核、导入与数据服务 |
| OPS | `scripts/windows/**` 与受管运行记录 | 启停、版本/PID/健康校验、网络诊断 |
| Control | `docs/control/**` | 任务治理、接口冻结、合并与验收 |

`contracts/**` 是共享契约。任何字段、状态、错误码或版本调整都必须包含 schema、版本、变更记录、兼容说明和受影响线路复核，不能作为普通跨线“顺手修复”。

## Git 与 Worktree

1. 开始工作前确认正式主仓库、目标分支、`HEAD`、`origin/develop` 和工作树状态。
2. 正式主仓库有用户未提交内容或正在提供服务时，创建独立 worktree；不在运行实例中直接改动。
3. 不执行 `reset --hard`、强制覆盖、随意清理工作树或删除未知文件。保留用户的配置、数据、日志和运行证据。
4. 每个任务只覆盖授权目录；遇到所有权或接口边界不明确时先冻结接口或升级到 Control。
5. 提交前核对差异范围、敏感文件和构建产物；禁止提交 `.env`、`config.local.ps1`、`.runtime`、数据库、向量库、日志、模型、依赖目录和客户数据。

推荐提交格式为 `type(scope): concise change`，例如 `docs(control): establish knowledge foundation`。合并前由 Control 记录依赖、测试证据和回滚点；未经授权不直接合并到 `develop`。

## PR 规范

PR 描述至少说明：目标与范围、明确不做什么、涉及的接口/数据、测试命令及结果、人工验收步骤、风险/回滚说明。跨线 PR 必须引用 `docs/control/interfaces/` 中冻结版本；接口文档不存在时不得开始跨线实现。

审查时重点检查：

- 是否越过 A/B/C/OPS 的目录所有权；
- 是否把 Mock、静态演示值或空数据伪装为真实业务结果；
- 是否扩大为自动发送、退款、售后、订单修改、ERP 写入、训练或发布；
- 是否携带敏感资料、运行产物或不可回滚迁移。

## 测试规范

按改动范围选择最小且充分的验证，而不是把文档变更误称为全系统测试：

| 区域 | 常用验证 |
| --- | --- |
| A | 对应 `backend` 虚拟环境中的 `pytest`，必要时真实 Ollama smoke |
| B | `frontend` 的 typecheck、Vitest、production build 与实际客服流程 |
| C/Admin | `platform_backend` 的 API/迁移测试；`admin_web` 的 typecheck、Vitest、production build 与页面路由 |
| OPS | PowerShell 语法、受管启动/状态/停止闭环、PID/监听/健康/版本一致性 |
| 文档 | Markdown 链接、JSON/YAML 语法、`git diff --check`、事实来源核对 |

测试通过不等于可以宣布生产可用。需要真实模型、数据、浏览器、局域网或人工流程的结论必须给出环境与证据，未验证则明确标记为未验证。

## 发布与运行

发布代码与切换运行实例是两个独立 Gate。Runtime Gate 要同时确认：工作目录、Git SHA、受管 PID、监听 PID、命令/路径、健康检查、页面入口和必要的真实闭环。不要因页面可打开就假定服务来自正确版本。

受管脚本和安全边界见[本机启动与故障排查手册](../operation/troubleshooting.md)。
