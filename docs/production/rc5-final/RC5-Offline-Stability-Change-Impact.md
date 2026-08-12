# RC5 Offline Stability Change Impact

## 变更边界

本轮没有修改 Gateway、ExecutionPreparation、ACK/Cursor、Agent Identity 或 Device Binding 公共协议，没有接触真实 PDD，也没有启用真实发送。

| 变更 | 为什么 | 影响 | 重新验收 |
|---|---|---|---|
| Platform 迁移 head 0019 | 增加数据库内部身份 | Platform DB schema | Platform 全量、迁移克隆、启动失败关闭 |
| Engine runtime identity | 防止错库/空库 | Host 启动配置 | Engine 全量、升级/恢复单测 |
| Projection Reconciler | 修复跨库崩溃窗口 | Host worker 启动 | 三个故障注入窗口、离线黑盒 |
| Runtime Backup Barrier | 取得一致静默切面 | 离线 Runtime 维护入口 | in-flight drain、epoch、integrity |
| Acceptance Knowledge bootstrap | 正式启动不再依赖测试资产 | Windows 启动流程 | PowerShell 合同、Backend/Platform 全量 |
| PDD 本地 Token | 保留订单关联但不暴露原值 | REAL_PDD Observation 校验 | 隐私、provider、mapper 回归 |
| 分层 verifier | 缩短日常反馈时间 | 开发/冻结流程 | Quick 和 Full 均实跑 PASS |
| Windows 事务升级 | 消除文件锁导致的新旧文件混装 | 安装目录切换，不改 DataRoot | 安装器单测、13 项隔离部署、当前实例 11 项保护对比 |
| 构建缓存清理 | 避免无用 `.pyc` 导致包膨胀与长路径失败 | Windows 候选包 | 包内清单、独立运行、隔离部署 |

## 会触发完整重新验收的修改

- 数据库 identity/revision/schema fingerprint 逻辑；
- Buffer、Decision、Assistant Snapshot 任一投影；
- Gateway、ACK/Cursor、Execution 安全门；
- REAL_PDD privacy/token/Provider 边界；
- 绿色助手 Decision/Preparation 展示；
- Windows 安装、升级、数据保留和候选包 Composition。

## 不允许混淆的版本事实

- 实现冻结点：Engine `43d6e9474163eb736713dba6156bc86cc4eef9e9`；AI-CS `ed7c7b804cb5d5d1d55aab202cf4ae8398231028`。本报告自身的后续文档提交不改变候选包。
- 新候选包：`f4cdd3162309c268498f4f7f2fa3f10c1ec3437472e4d1ac7e106680c213352e`。
- 已安装 Agent 已用该候选包事务式覆盖升级；Manifest、EXE、PYZ 与候选包一致。升级前后保护对比 11/11 PASS。
