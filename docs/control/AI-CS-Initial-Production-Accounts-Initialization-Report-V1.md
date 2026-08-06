# AI-CS Initial Production Accounts Initialization Report V1

> 审计日期：2026-08-06
> 需求：R017 AI-CS User Initialization V1
> 执行结论：`FAIL / ZERO_WRITE`
> 当前状态：`AI_CS_INITIAL_ACCOUNTS_BLOCKED`

> R018 后续更新：账号格式、临时口令首次改密、客服多 Store、运营/管理员全 Store和客服管理权限策略已经由 `AI_CS_ACCOUNT_POLICY_READY` 关闭；下文关于旧 R016 规则冲突的描述仅保留为本次只读审计发生时的历史证据。正式 Runtime 仍为0012/pre-IAM，三个账号仍未创建，因此本报告的`FAIL / ZERO_WRITE`结论不变。

## 1. 结论

本轮没有创建、覆盖或修改任何账号、角色、Session、店铺绑定或数据库记录。当前受控 Runtime 数据库仍为 `0012_internal_production_finalization_v1`，IAM 所需的 `0013_user_management_v1` 尚未部署，运行中的 C 服务也未提供登录身份端点。因此，初始化的必要前置条件不成立，不能声明 `AI_CS_INITIAL_ACCOUNTS_READY`。

直接绕过应用校验写 SQLite、降低用户名或密码规则、在命令行/文档中传递凭证，都会破坏 R016 的安全边界，本轮均未执行。

## 2. 创建账号列表

| 账号目标 | 目标角色 | 本轮状态 | 说明 |
| --- | --- | --- | --- |
| 超级管理员候选 | `ADMIN` | `NOT_CREATED` | 数据库未迁移到0013；旧规则冲突已由R018解决。 |
| 客服主管候选 | `CUSTOMER_SERVICE` | `NOT_CREATED` | 数据库未迁移到0013；旧用户名/口令规则冲突已由R018解决。 |
| 运营主管候选 | `OPERATOR` | `NOT_CREATED` | 数据库未迁移到0013；旧用户名/口令规则冲突已由R018解决。 |

敏感信息控制：本报告不记录明文密码、密码 hash、Session token 或完整认证材料。重复账号检查因 `users` 表尚不存在而无法进入应用层执行；不存在任何覆盖行为。

## 3. 角色分配与权限判断

本轮角色分配数量为零。

- `ADMIN`：R016 固定角色包含全部系统权限和用户管理权限。
- `CUSTOMER_SERVICE`：当前固定权限仅为 Workspace 访问、AI 回复和 Feedback 提交；需求中的“客服相关管理”不是该角色现有权限。若附加 `OPERATOR`，会同时扩大到商品、知识和 Feedback 查看，必须另行明确授权。
- `OPERATOR`：当前固定权限覆盖商品管理、知识管理和 Feedback 查看；SKU 与 AI 问题页面需要按现有服务端 permission 映射验收。R016 V1 的运营授权是角色级全局权限，Store binding 尚不构成运营 API 的行级权限边界。

## 4. 店铺绑定状态

只读审计确认当前数据库存在两个已启用 Store：`汕明`、`玩趣乐园积木店`。本轮未创建虚假店铺，也未新增绑定。

| 账号目标 | 绑定状态 | 待确认项 |
| --- | --- | --- |
| 超级管理员候选 | `NOT_REQUIRED_BY_ROLE` | `ADMIN` 由角色获得全部店铺权限，无需伪造“全店绑定”。 |
| 客服主管候选 | `WAITING_FOR_STORE_BINDING` | 必须明确指定两个现有 Store 中哪一个是唯一默认客服店铺。 |
| 运营主管候选 | `WAITING_FOR_STORE_BINDING` | 必须明确绑定一个还是两个现有 Store；同时确认接受 V1 运营权限仍为角色级全局权限。 |

## 5. 登录、Session 与 RBAC 验证

| 验证项 | 结果 | 证据 |
| --- | --- | --- |
| 管理员登录与角色 | `NOT_RUN` | 账号未创建，运行服务无 IAM 端点。 |
| 客服登录与角色 | `NOT_RUN` | 账号未创建，运行服务无 IAM 端点。 |
| 运营登录与角色 | `NOT_RUN` | 账号未创建，运行服务无 IAM 端点。 |
| Session 创建 | `NOT_RUN` | `/api/v1/auth/me` 在当前 C Runtime 返回 HTTP 404。 |
| RBAC 与权限隔离 | `NOT_RUN_IN_RUNTIME` | R016 源码自动化 Gate 已通过，但不能替代当前生产 Runtime 验收。 |

## 6. 数据库与 Runtime 状态

- 受控配置：Windows `green-standard.local.ps1`，SQLite，数据库文件存在。
- 当前 Alembic revision：`0012_internal_production_finalization_v1`。
- 目标 revision：`0013_user_management_v1`，当前未应用。
- IAM 表：`users`、`roles`、`user_roles`、`user_store_bindings`、`user_sessions` 均不存在。
- 数据库完整性：`PRAGMA integrity_check = ok`。
- Runtime：5173、5174、8000、8011 均为 loopback 监听；C `/health` 正常，但身份端点返回404，表明运行服务仍是 pre-IAM 版本。
- Source identity：当前分支存在80项未提交变更，R016 Candidate 尚不是可由 CLEAN Gate 部署的受控 source identity。

## 7. 输入校验缺口

R016 当前源码规则要求用户名匹配 `^[A-Za-z0-9._-]{3,64}$`，创建用户密码长度为12–128字符。用户给出的三个目标密码均短于最低要求；两个非管理员目标用户名分别违反最短长度和字符允许列表。禁止通过直接 SQL、临时改规则或明文落盘绕过。

## 8. 解除阻塞条件

1. 单独授权把 R016 dirty Candidate 固化为受控提交，并对正式数据库先备份、再执行0012→0013迁移与 Runtime 切换。
2. 提供符合当前规则的两个非管理员用户名；管理员用户名可保留现有目标。
3. 为三个账号提供各自唯一的12–128字符密码。凭证应由用户放入 Git ignored Runtime 文件，或授权系统生成并保存在该区域；不得继续写入聊天、命令行、文档或 Git。
4. 指定客服主管的唯一默认 Store，并指定运营主管绑定一个还是两个现有 Store。
5. 明确客服主管保持纯 `CUSTOMER_SERVICE`，还是接受增加 `OPERATOR` 带来的更广权限；若需要“客服管理”独立权限，应另立 RBAC Contract 变更任务。
6. 迁移后先执行重复账号检查，存在即停止且不覆盖；随后创建、登录、Session、401/403、Store 自动进入与跨角色权限隔离全部通过，才可升级状态。

## 9. 安全审计记录

- 访问理由：执行初始生产账号初始化前置核验。
- 访问范围：受控配置、Runtime health、Schema revision、表存在性、Store 最小目录与数据库完整性。
- 实际结果：只读检查完成，数据库零写入，账号零创建，Session 零创建，未输出密码 hash/token。
- Task Gate：`FAIL`；修复任务见 [R017 Remediation Task Card](product-management/AI-CS-Initial-Production-Accounts-Remediation-V1-Task-Card.md)。

Final Status: `AI_CS_INITIAL_ACCOUNTS_BLOCKED`
