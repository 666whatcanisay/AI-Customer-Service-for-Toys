# RC5 Database Final State Report

> 2026-08-12 更新：源码 Migration Head 与 R027/Standard 两个 Platform 运行库均已受控升级为 `0019_runtime_database_identity_v1`；Channel Engine 为 `runtime_storage_version=1.0` 并完成内部身份 + sidecar 双向绑定。详情以 [RC5 Offline Stability Readiness Report](RC5-Offline-Stability-Readiness-Report.md) 为准，旧正文的 0018/0013 描述仅是历史快照。

## 结论

数据库离线验收 **PASS**。源码 Migration Head 与当前运行测试库均为 `0018_store_platform_bindings_v1`；完整性为 `ok`，外键违规为 `0`。验证没有修改生产数据库。

| 项目 | 结果 |
|---|---|
| 源码 Migration Head | `0018_store_platform_bindings_v1` |
| 当前运行测试库 | `0018_store_platform_bindings_v1`；48 表；integrity `ok` |
| 历史样本库 | `0013_user_management_v1`；仅用于升级克隆测试 |
| 空库升级/降级/再升级 | PASS |
| 0013 克隆升级/降级/再升级 | PASS，保护数据行数不变 |
| 0018 当前库克隆幂等升级 | PASS |
| 验证期间生产库变更 | `0` |

## 是否允许升级 Pilot/生产库

允许进入受控升级演练，但必须先做文件级备份、记录 SHA256、停止写入、在克隆库预演、核对 revision/integrity/foreign keys，再升级真实 Pilot 库。没有备份或回滚窗口时不允许升级。

证据：`.runtime/rc5-final/migration-matrix/migration-matrix.json`。
