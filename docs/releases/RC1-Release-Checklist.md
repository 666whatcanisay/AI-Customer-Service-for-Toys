# Channel Engine RC1 Release Checklist

Release candidate：`0.1.0rc1`

Gateway Contract：wire version `1.0`

Frozen canonical SHA-256：`e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`

## Repository

- [x] 项目版本统一为 `0.1.0rc1`。
- [x] 直接依赖使用精确版本，RC1 验证环境已写入 `requirements-rc1.lock`。
- [x] README、Release Notes、Changelog、Deployment Guide、Rollback Guide 完整。
- [x] RC1 显式文件白名单已建立：368 个仓库基线文件，其中 351 个为本次暂存候选。
- [x] 排除 87 个 evidence、生成报告和本地试点配置（含 2 个暂存差异证据文件）；删除项为 0。
- [x] 暂存流程逐文件读取白名单，禁止使用 `git add .`。
- [ ] 工作树无 tracked modification 和 untracked release input。
- [ ] 被验证源码已进入新的受保护提交并具备可引用的 RC1 tag。

## Runtime

- [x] 启动、状态、Heartbeat、降级、恢复和停止专项通过。
- [x] 持久化恢复、Outbox 恢复和 Kill Switch 恢复专项通过。
- [x] `/health` 与 `/runtime/v1/status` 返回安全状态。

## Contract

- [x] Gateway Contract wire version 保持 `1.0`。
- [x] canonical SHA 保持冻结值。
- [x] Cross Repository Validation 已通过。
- [x] 未增加 schema 字段。

## Security

- [x] `real_platform_activation_allowed=false`。
- [x] `activation_grant_issued=false`。
- [x] `real_send_enabled=false`。
- [x] Agent RC 默认 `kill_switch=true`、`manual_approval=true`、`auto_reply=false`。
- [x] Credential 仅保存 reference。
- [x] RBAC 角色为 Operator、Supervisor、Admin。
- [x] 最终 security suite 与敏感信息扫描通过。

## Test Freeze

- [x] Full pytest regression：508 passed，0 failed，1 warning。
- [x] Contract suite：123 passed，0 failed。
- [x] Security suite：17 passed，0 failed。
- [x] `compileall`：PASS。
- [x] RC1 verification gate 已执行；当前因 `SOURCE-001` 返回 BLOCKED。

## Release Decision

**当前判定：BLOCKED。** 唯一 Gate blocker 是 `SOURCE-001`：RC1 Source Freeze 候选已经完成分类，但尚未由发布负责人确认提交，也尚未形成受保护 RC1 commit/tag。

只有以上所有复选项完成，且 `verify_channel_engine_rc1.py` 返回 `READY` 时，才允许发布 `CHANNEL_ENGINE_RC1_READY`。测试通过不能替代干净、受保护的源码基线。
