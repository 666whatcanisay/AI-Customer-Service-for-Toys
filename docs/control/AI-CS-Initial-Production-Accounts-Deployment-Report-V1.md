# AI-CS Initial Production Accounts Deployment Report V1

> 执行日期：2026-08-06
>
> 需求：R019 Production IAM Deployment & Initial Accounts V1（关闭 R017）
>
> Task Gate：`PASS`
>
> 最终状态：`AI_CS_INITIAL_ACCOUNTS_READY`

## 1. 结论

正式 Runtime 已从 `0012_internal_production_finalization_v1` 受控迁移到 `0013_user_management_v1`，三个批准的初始账号已经通过系统 IAM 服务创建。真实登录、强制首次改密、Session 撤销、服务端 RBAC、客服多店选择与恢复空绑定、运营/管理员全店范围均通过。

整个过程未创建虚假 Store，未覆盖重复账号，未通过直接 SQL 创建账号，未输出或提交明文口令、密码 hash、Session token、数据库、备份或 Runtime 回执。Gateway Contract V1、`/api/chat`、R006、R009、商品知识、Prompt、模型与 RAG 数据语义未修改。

## 2. 源码与 Runtime 身份

| 项目 | 结果 |
| --- | --- |
| 分支 | `release/product-reliability-hardening-v1` |
| IAM 受控基线 | `ed12da9ab6340767f930bac3479ee87d21204643` |
| IAM-safe 启动修复 | `dda708b7447ee92c8e38bd888e928468866f43c3` |
| IAM-safe package readiness 修复 | `fc4f6d97c87261b434f5a15b119b24f8964803bf` |
| 配置 | `.runtime/phase-e/config/green-standard.local.ps1`（Git ignored） |
| 正式数据库 | `.runtime/phase-e/data/standard-platform.sqlite3`（Git ignored） |
| 网络模式 | `LOCAL`；B 5173、Admin 5174、A 8000、C 8011 |

首次在 IAM source 上启动时，旧启动 smoke 匿名访问了已受 IAM 保护的测试数据包端点并收到 401；wrapper 按设计自动清理了已启动进程，没有留下半启动状态。修复仅把启动期 package/RAG readiness 改为既有 loopback-only 冻结接口，不降低 IAM 鉴权，不改变业务 API、Gateway wire 或 RAG 内容。

## 3. 迁移前备份

| 证据 | 值 |
| --- | --- |
| 备份时间（UTC） | `2026-08-06T08:19:22.4107268Z` |
| 备份路径 | `.runtime/phase-e/green-standard/pilot-backups/platform-20260806-161922.sqlite3` |
| 源数据库迁移前 SHA-256 | `b7f5ff784f1414275157fdfa4b8f2f67bf888cc48f0e8cf1a6ac525020586809` |
| 备份 SHA-256 | `76db33df3417bc046e6fdf35eddf83181e66be03874319e2508bb3f7153cf360` |
| 大小 | 源与备份均为 `1,785,856` bytes |
| Schema / 完整性 | `0012_internal_production_finalization_v1` / `ok` |
| 逻辑核对 | 37 个迁移前表的行数一致；2 个既有 Store 保留 |

备份通过 SQLite online backup 生成。在线源文件与备份文件的字节级 hash 可以因 SQLite 页布局不同而不同；本次以文件长度、revision、`integrity_check`、表集合和逐表行数共同证明逻辑一致性。

## 4. 数据库迁移结果

- 迁移完成时间（UTC）：`2026-08-06T08:19:49.3072267Z`。
- 当前 revision：`0013_user_management_v1`。
- IAM 表：`users`、`roles`、`permissions`、`role_permissions`、`user_roles`、`user_store_bindings`、`user_sessions` 全部存在。
- 固定目录：3 个角色、12 个权限、23 条 role-permission 映射，与服务端固定 RBAC 矩阵一致。
- 迁移后原 37 个业务表逐表行数与迁移前备份一致；既有 2 个 Store、24 个 Product、18 个 SKU 以及导入、activation、publication、知识数据均保留。
- 初始账号验收结束并停止服务后的数据库 SHA-256：`ee4fc4425a57c5d877f25cb90dc38213be2cd7b850d41af159f453b129fa41ae`；大小 `1,900,544` bytes；`integrity_check=ok`。

## 5. 账号创建结果

| Username | Display name | Role | 状态 | 首次改密 | 创建结果 |
| --- | --- | --- | --- | --- | --- |
| `admin` | 超级管理员 | `ADMIN` | `ACTIVE` | 必须 | `CREATED` |
| `Wa` | 客服主管 | `CUSTOMER_SERVICE` | `ACTIVE` | 必须 | `CREATED` |
| `江` | 运营主管 | `OPERATOR` | `ACTIVE` | 必须 | `CREATED` |

初始化使用 `bootstrap_ai_cs_initial_users.ps1` 的交互式安全输入。脚本在创建前按规范化用户名检查重复，重复时只跳过、不覆盖；本轮三项均为首次创建。数据库只保存系统生成的 salted password hash，本报告不显示 hash 或认证材料。

## 6. 权限与店铺范围

| 账号 | 服务端权限验证 | Store 结果 |
| --- | --- | --- |
| `admin` | 登录、首次改密门禁、用户管理、全权限通过 | `all_store_access=true`；0 条显式绑定 |
| `Wa` | 登录、首次改密门禁、客服 Workspace/客服管理范围通过 | `all_store_access=false`；可见 2 个已启用客服 Store；多店选择通过，验收后由管理员恢复为 0 条固定绑定，首次正式使用进入选择流程 |
| `江` | 登录、首次改密门禁、运营资源读取通过 | `all_store_access=true`；0 条显式绑定 |

全店范围来自 `ADMIN` / `OPERATOR` 的角色语义，不伪造“绑定全部店铺”记录。`CUSTOMER_SERVICE` 自助选择接口按 Contract 至少选择一个 Store；验收后的空初始状态通过管理员用户管理接口恢复。

## 7. 登录、Session 与安全验证

- 三个账号均通过正式 C Runtime 的 `/api/v1/auth/login` 登录并得到预期角色。
- 三个账号在初始化状态均投影 `must_change_password=true`；受保护业务接口在改密前保持 fail-closed。
- 验收使用随机、仅内存存在的替换口令测试改密和重新登录；随后由正式管理员 API 恢复批准的初始状态。
- 改密使旧 Session 失效；验收结束主动 logout，最终 active Session 数量为 `0`。已撤销的 token digest 审计记录按现有保留策略留在数据库，不包含可复用 token。
- 最终数据库状态：3 users、3 user_roles、0 user_store_bindings、0 active sessions，完整性 `ok`。

## 8. 测试与兼容证明

| Gate | 结果 |
| --- | --- |
| C 全量 | `130 passed` |
| C IAM/permission migration focused | `9 passed` |
| A 全量 | `147 passed, 3 skipped`（仅 opt-in real E2E） |
| B | `34 files / 143 tests`，typecheck、production build PASS |
| Admin | `33 files / 84 tests`，typecheck、production build PASS |
| Shared contracts | `10 passed`；repository `0.10.0 / coordinated` |
| Windows IAM policy / Runtime entry | PASS |
| 正式 Runtime | start/status/stop、C health、0013、登录、改密、RBAC、Store scope PASS |
| RAG 保护 | `test_knowledge_v031=56 chunks`、model ready；未 sync、未清空、未重建 |
| Gateway 保护 | Gateway wire `1.0` 与 canonical schema 未修改；未连接生产 Channel Engine/PDD |

B 客服仍通过经 C 鉴权的 Workspace 调用链访问 A `/api/chat`，人工确认与不自动发送语义保持不变。Operations Console、A、B、C 在同一 clean source identity 下由标准 wrapper 管理。

## 9. 回滚方式

仅在明确回滚授权后执行：

1. 使用 `scripts/windows/stop_ai_cs_server.ps1` 停止四个受管服务，确认 5173/5174/8000/8011 已释放；禁止在 SQLite 被写入时直接覆盖。
2. 对失败现场数据库先创建 Git ignored 审计副本并记录 hash、revision、完整性；不要删除现场文件。
3. 核对目标路径严格为 `.runtime/phase-e/data/standard-platform.sqlite3`，再用迁移前备份 `platform-20260806-161922.sqlite3` 恢复。
4. 恢复后验证备份 hash、`0012_internal_production_finalization_v1`、`integrity_check=ok` 和原 37 个业务表计数。
5. 数据库回退到0012时必须同时切换到兼容的 pre-IAM source（本任务前锚点 `0e422c50`），或完成经过验证的 forward migration；不得让 0013 IAM source 长期运行在0012数据库上。
6. 标准启动并重新验证四服务、RAG 56 chunks 和 source identity。恢复0012会整体撤销0013 IAM表、三个账号、Session和Store binding，但不会删除迁移前已有业务/RAG资产。

## 10. 剩余风险与下一步

- 初始口令是临时凭证；三个账号首次正式使用必须立即改为各自独立长期口令。不要把长期口令写入脚本、聊天、日志或 Git。
- 当前为受控 LOCAL Runtime 验收；LAN 员工访问仍需遵循现有精确 Windows Firewall / private CIDR Gate，不能扩大到公网。
- 账号停用、密码轮换、Session 保留期和安全审计导出应进入后续日常 IAM 运维制度。
- R003 完整业务验收和 R007 第二终端网络验收仍是独立 Gate，不由本任务关闭。

Task Gate：`PASS`

Final Status: `AI_CS_INITIAL_ACCOUNTS_READY`
