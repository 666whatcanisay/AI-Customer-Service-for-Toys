# RC5 Database Final State Report

## 结论

数据库离线验收 **PASS**。源码 Migration Head、R027 Platform Runtime 和 Standard Platform Runtime 均为 `0019_runtime_database_identity_v1`；Channel Engine Host 使用 `runtime_storage_version=1.0`。所有已验收数据库完整性为 `ok`，外键违规为 `0`。

| 项目 | 最终状态 |
|---|---|
| 源码 Migration Head | `0019_runtime_database_identity_v1` |
| R027 Platform Runtime | `0019`；49 表；integrity `ok` |
| Standard Platform Runtime | `0019`；49 表；integrity `ok` |
| Channel Engine Host | storage `1.0`；identity revision `1`；integrity `ok` |
| 普通启动自动迁移 | 禁止；只校验身份和 revision |
| 日常启动绑定 | instance ID + role + environment + schema fingerprint + canonical path + revision |
| 整库 SHA | 仅用于备份、迁移和 Release Evidence |

## 身份规则

- 数据库内部 metadata 与 `RuntimeDatabaseBindingV1` sidecar 双向核验。
- 开发/测试 Clone 生成新的 `database_instance_id`。
- 正式灾备 Restore 保留逻辑数据库 ID，并增加 `restore_generation` 和 `restored_from_backup_epoch`。
- sidecar 与数据库、环境或 canonical path 不一致时 fail-closed。

## 受控迁移与备份

两个 Platform 数据库和 Engine 数据库均使用：停止监听 → 在线备份 → 克隆预演 → 显式迁移/升级 → 身份双向校验。多库 Runtime Backup 使用静默屏障：停止新 Observation、等待 in-flight 归零、Projection 对账、记录统一 `backup_epoch` 后分别在线备份。

证据位于 `.runtime/rc5-offline-stability/database-upgrade/` 与版本矩阵；数据库和备份本身均保持 Git 忽略。
