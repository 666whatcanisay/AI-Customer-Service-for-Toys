# AI-CS PDD 首次受控激活运行手册 V1

## 适用范围

本手册只用于首次真实 PDD **Observe Mode** 激活。它不授权读取客户消息、不授权
发送、不授权自动回复，也不授权订单或资金动作。

## 1. 人员与批准

一次窗口必须有三名不同主体同时在线：

- Operator：执行步骤和状态观察；
- Supervisor：批准单店范围、时间窗和 Selector evidence；
- Admin：批准 Credential/RBAC/Kill Switch，并负责紧急隔离。

任何一人缺席，窗口取消。不得共用账号、代批或离线预批。

## 2. 什么时候开始

只在以下条件同时满足时开始：

1. 变更记录已批准，明确单店、单账号、单实例、单 Browser Session；
2. 激活窗口为 15 分钟至 4 小时，三名责任人全程在线；
3. 客服低峰期，现场可以立即人工接管；
4. Kill Switch 已开启，Execution creation 和 Outbound transport 已关闭；
5. 回滚责任人已复述停止顺序；
6. 离线检查输入由受信任控制面导出，不含 Cookie、Token 或 Password。

## 3. T-30 分钟：离线 Preflight

1. Admin 确认 `real_platform_activation_allowed=false`，且没有 activation grant；
2. Operator 导出受控检查 JSON；不得手填 store id 或 credential material；
3. 运行：

   ```powershell
   .\.venv\Scripts\python.exe scripts\check_pdd_controlled_activation.py `
     --input <受控检查文件> --output <Evidence 文件>
   ```

4. 退出码 `1` 或 `2` 时立即取消窗口；
5. Supervisor 审阅 Plan fingerprint、Scope、Window 和 Gate 顺序；
6. Admin 审阅 signed Gateway health、Credential/RBAC、安全策略和回滚计划。

检查器返回 `0` 也不表示已获准连接，仅表示可以进入后续人工证据流程。

## 4. T-10 分钟：人工登录与身份核验（后续获批任务执行）

本步骤当前未执行。后续任务获批后：

1. Operator 启动指定的独立 Chrome Profile；
2. Operator 人工扫码/登录；系统不得自动输入或导出 Cookie；
3. 只读获取 Store identity；
4. 将观察到的 Store identity 与 `store-binding-ref` 指向的批准身份比对；
5. 不匹配或无法确认时，触发 `STORE_IDENTITY_MISMATCH` 并立即回滚；
6. 不得打开第二店铺、第二账号、第二实例或第二 Browser Session。

## 5. Selector Discovery（只读）

1. Selector 必须从 `DRAFT` 进入 `DISCOVERY`；
2. 仅采集登录状态、店铺身份、页面状态和必要的结构元数据；
3. 不点击发送、不输入回复、不调用订单功能；
4. Supervisor 核验 evidence；
5. 未达到 `VERIFIED`、出现漂移或 UNKNOWN 时立即停止；
6. synthetic evidence 不能用于 Production Observe grant。

## 6. 最终人工批准

在同一时间窗内：

1. Supervisor 对当前 Plan fingerprint、Store identity 和 Selector evidence 批准；
2. Admin 对 Credential/RBAC/Kill Switch/Execution disabled 状态批准；
3. 两份批准必须短时有效，且 principal 不同；
4. 拒绝或过期即取消；
5. 受信任控制面另行签发短时 receive-only Observe grant。

检查器、Operator 或 Browser Runtime 都不得自行签发 grant。

## 7. Observe Mode 运行纪律

- 页面只读；
- `auto_reply=false`；
- `send_enabled=false`；
- `execution_creation_enabled=false`；
- `channel_kill_switch_enabled=true`；
- 当前首次窗口不读取客户消息；
- 每 1 分钟确认 Runtime、Session、Adapter、Cursor、Gateway 状态；
- 不在日志或 Evidence 中保存客户内容、Cookie、Token、Password。

## 8. 如何停止

任何 Operator 可提出停止；Admin 执行第一步，随后按顺序完成：

1. 关闭 Execution creation，确认 `PDD_EXECUTION_CREATION_DISABLED`；
2. 停止 Adapter，确认 `PDD_ADAPTER_STOPPED`；
3. 停止 Session/Browser，确认 `PDD_SESSION_STOPPED`；
4. 隔离该实例 Gateway 请求，确认 `PDD_GATEWAY_ISOLATED`；
5. 封存 Evidence，确认 `PDD_EVIDENCE_SEALED`；
6. Supervisor 标记 `PDD_MANUAL_VERIFICATION_REQUIRED`。

不删除 Receipt、Event、Audit、Cursor 或 Runtime history。

## 9. 立即停止条件

出现任一条件不做自动恢复：

- 激活窗口到期；
- Store identity mismatch/unknown；
- Selector unknown/drift；
- Session expired/failed；
- Cursor unknown、missing sequence 或持久化状态不确定；
- Gateway unhealthy 或 contract mismatch；
- 检测到 Execution、Outbound、Send 或 click-send 路径被启用；
- 任一责任人要求停止。

## 10. 如何恢复

1. 保持 Execution disabled 和 Gateway isolated；
2. Supervisor 完成 Evidence 复核并给出故障分类；
3. 修复问题，但不复用过期 approval/grant；
4. 新建变更记录或更新授权窗口；
5. 重新导出 Credential/RBAC/Runtime/Gateway/Selector 证据；
6. 从第一道 Preflight 重新开始；
7. UNKNOWN 状态禁止自动 reconnect 或自动重试。

## 11. Evidence 签收

窗口关闭前应具有：

- Plan fingerprint 与批准窗口；
- 三个不同 principal 的非敏感身份引用；
- Runtime/Session/Adapter/Cursor/Gateway 状态；
- Credential reference status；
- Selector state 和 evidence reference；
- 六道 Gate 结果；
- 停止步骤及每步 verification code；
- 零副作用证明：browser/network/message-read/send 均为 0（仅限离线检查阶段）。

缺少任一项，运行标记为 `MANUAL_INTERVENTION`，不得恢复。
