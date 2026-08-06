# R019 AI-CS Production IAM Deployment & Initial Accounts V1 Task Card

## 任务身份

- Requirement ID：`R019`
- 状态：`DONE`
- 当前 Gate：`AI_CS_INITIAL_ACCOUNTS_READY`
- Owner：Control / OPS / C IAM / QA
- 创建日期：2026-08-06

## 目标

把已验证的R016/R018 IAM候选固化为受控CLEAN源码，备份正式0012 SQLite，迁移0013，协调切换四服务，安全创建三个批准账号，并验证首次改密、RBAC与Store范围，最终达到`AI_CS_INITIAL_ACCOUNTS_READY`。

## 前置事实

- 正式数据库为`.runtime/phase-e/data/standard-platform.sqlite3`，迁移前revision为`0012_internal_production_finalization_v1`。
- 四服务迁移前可用，但运行记录显示源码`DIRTY / fingerprint mismatch`；正式启动Gate禁止在dirty source上切换。
- A基线为`test_knowledge_v031=56 chunks`，模型ready；本任务禁止重建知识或向量。
- 原0013缺少需求明确要求的`permissions`持久化目录；在首次正式迁移前补齐`permissions`和`role_permissions`，并锁定其与服务端固定RBAC矩阵一致。

## 执行Gate

1. 精确审计并提交R016/R018/R019源码，不使用`git add .`，排除数据库、runtime、secret、日志、依赖和构建产物。
2. 安全停止现有受管四服务；通过SQLite online backup创建可恢复备份，记录UTC时间、路径、长度、SHA-256、revision和`integrity_check`。
3. 只对受控正式数据库执行0012→0013；验证users、roles、permissions、role_permissions、user_roles、user_store_bindings、user_sessions及固定种子。
4. 从同一CLEAN SHA协调启动B/C/Admin/A，确认C使用同一正式数据库，A集合/chunks和Gateway wire不变。
5. 通过`bootstrap_ai_cs_initial_users.ps1`交互输入临时口令；重复账号只跳过不覆盖，不在参数、日志、报告或Git中记录口令/hash/token。
6. 验证三个账号登录、首次改密403 Gate、角色权限、客服空绑定和可选Store、运营/管理员全Store；验证后撤销测试Session，不输出token。
7. 形成部署报告、回滚说明和状态同步；只有全部证据通过才声明Ready。

## 回滚边界

- 账号创建前迁移失败：停止服务并用已校验备份恢复数据库，保持源SHA不变后重新启动0012兼容版本。
- 账号创建后回滚：先停止服务并保留失败库审计副本，再恢复迁移前备份；恢复会整体撤销0013表、账号、Session和绑定。
- 禁止直接SQL修补账号、复制测试库、删除Store/商品/知识、清空向量或自动重建RAG。

## 执行记录

- 精确提交R016/R018/R019源码为`ed12da9`；IAM-safe Runtime修复为`dda708b`、`fc4f6d9`。数据库、runtime、secret、日志、依赖、构建产物均未进入Git。
- 迁移前备份：`.runtime/phase-e/green-standard/pilot-backups/platform-20260806-161922.sqlite3`，revision 0012、完整性ok、逐表逻辑核对通过。
- 正式数据库已迁移0013；7个IAM表、3角色、12权限、23条映射存在，迁移前37个业务表计数保持一致。
- 三个批准账号创建成功；登录、首次改密、Session撤销、RBAC、客服2店多选并恢复空绑定、运营/管理员全店通过。
- 最终为3 users、3 user_roles、0 Store bindings、0 active sessions；数据库完整性ok；RAG仍为56 chunks，未重建。
- Task Gate：`PASS`。完整证据见[Deployment Report](../AI-CS-Initial-Production-Accounts-Deployment-Report-V1.md)。

Final Status: `AI_CS_INITIAL_ACCOUNTS_READY`
