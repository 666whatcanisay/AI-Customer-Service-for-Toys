# AI-CS Server Release Candidate Stabilization V1 Task Card

| 字段 | 内容 |
| --- | --- |
| 需求 ID | R014 |
| 日期 | 2026-08-05 |
| Owner | AI-CS Production Server Release Engineer；A/OPS 主责，C Console、contracts 与 Control/QA 受影响复核 |
| 状态 | `DONE` |
| 目标 Gate | `AI_CS_SERVER_RELEASE_CANDIDATE_READY` |

## 目标

将保护锚点上的 R011–R013 dirty Server Candidate 精确分类、受控提交，并以 clean SHA 完成 Windows Production Server 的真实 start/status/Decision/Console/stop 验证。

## 完成标准

1. 所有 dirty 路径按 Gateway Runtime、Production Wrapper、Server Console、Contracts、Tests、Documentation 分类，无实验文件或非生产资产混入。
2. 禁止使用 `git add .`；cached diff 不包含数据库、`.runtime`、secret、日志、evidence、依赖或构建产物。
3. 保护锚点保持为受控提交的祖先；提交前 index tree 与提交后 tree 一致，最终 Git clean。
4. `start_ai_cs_server.bat`、status、Gateway Health/Decision/幂等、Console proxy 与 stop 在同一 clean SHA 上通过。
5. Gateway Contract V1 routes、schema 与 canonical SHA 不变；R006、R009、RAG、Prompt、B 客服和生产 Engine/PDD 不变。

## 验收证据

- Source commit：`6ae8d407fc22a8e2a8291fdbfa80706db4ae9f5d`；直接父提交为保护锚点 `0b3367f85999f1dc840accf23742c290eb53746b`。
- Windows PowerShell 5.1 fix commit：`4b6c0bd09de2cca25ae1cb2ca2af76da4455217b`。
- 四服务在 `4b6c0bd09de2`、`CLEAN`、`runtimeMode=standard`、`networkMode=LOCAL` 上全部 `RUNNING` 且身份已验证。
- Gateway `HEALTHY`、version `ai-cs-gateway.v1`、Contract `1.0`；合成 Decision HTTP 200、`requires_approval=true`、幂等回放同一 decision。
- A `138 passed, 3 skipped`；C R006/R009 定向 `25 passed`；Admin `76 passed` + typecheck/build；OPS `11/11`；contracts `7 passed`；17 schemas valid。
- 受管 stop 后 8011/8000/5173/5174 全部释放；Git 保持 clean。

## Gate

`PASS / AI_CS_SERVER_RELEASE_CANDIDATE_READY`

该 Gate 是本地受控 Release Candidate 与 Windows Runtime 验证结论，不表示已推送、打 tag、部署生产、完成 TLS/正式 secret manager，或连接生产 Channel Engine/PDD。
