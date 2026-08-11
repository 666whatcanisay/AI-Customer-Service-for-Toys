# ChannelAgent 2.0.0rc3 Runtime 稳定性升级验证报告

## 结论

ChannelAgent 已完成 `2.0.0rc1 → 2.0.0rc3` 受控原位升级，最终验证结果为 **PASSED**。

- Client Resource：`2.0.0rc3`
- Agent Runtime：`2.0.0rc3`
- Brand Asset：`1.0`
- Agent Control：`2.1`（未修改）
- Gateway Contract SHA：`e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`（未修改）
- RC3 正式包 SHA256：`62434af07e658c6e526de0384f46429017cea0ff7728db72882ad124b848b02f`
- RC1 Runtime 基线 SHA256：`a2f5f89f3656eeab2ad46deea39805de8d067e8978f5ee6f80e0f3839d75a31a`
- RC3 Runtime SHA256：`0bff9b96c008f6e529a7dcce6e07e8663912d3f54d5746366754e2db09230ed1`

## 修复内容

### Windows 快捷方式

- 正式名称统一为 `AI-CS 客服助手.lnk`。
- 安装、升级和卸载脚本通过 ASCII 安全的 Unicode 码点函数生成中文名称。
- 所有包含非 ASCII 内容的发布 PowerShell 脚本均使用 UTF-8 BOM，并通过 Windows PowerShell 5.1 解析。
- 只归档目标精确指向当前 `ChannelAgent.exe` 的已知乱码快捷方式。
- 当前桌面只保留一个指向正式客户端的 `AI-CS 客服助手.lnk`，Target、WorkingDirectory 和 IconLocation 均已校验。

### WindowsStateStore

- 增加进程内 `RLock`，序列化同一进程的状态读写。
- 对临时 `PermissionError` 和原子替换瞬间的 `FileNotFoundError` 实施最多 8 次有限重试。
- 退避从 20ms 开始，单次最多 250ms。
- 永久锁定返回 `LOCAL_STATE_TEMPORARILY_LOCKED`。
- JSON 损坏和文件超限继续 Fail Closed，不被当作临时锁重试。

### 原子替换与线程回收

- `os.replace` 被封装为模块内 `_atomic_replace`，测试不再修改全局 `os.replace`。
- Runtime 生命周期测试使用 `try/finally` 停止并回收线程。
- 升级器使用带合法备份路径的 `File.Replace`，避免 Windows PowerShell 5.1 将空备份路径转换为非法路径。

## 最小补丁边界

RC3 Runtime 从已批准的 RC1 pyz 基线生成，pyz 内仅有三个成员变化：

1. `channel_agent/binding.py`
2. `channel_agent/version.py`
3. `channel_agent/windows.py`

未混入 PDD Adapter、Gateway、Agent Control、登录、自动发送或当前 dirty workspace 中的其他业务变化。

## 测试结果

| 验证项 | 结果 |
|---|---:|
| Windows Client 与 Runtime Binding 回归 | 27 passed |
| Windows Runtime 连续稳定性 | 50/50 rounds passed |
| Python compileall | passed |
| PowerShell 脚本解析 | passed |
| PowerShell UTF-8 BOM Gate | passed |
| Windows PowerShell 5.1 中文快捷方式名称 | passed |
| RC3 pyz 最小差异 Gate | passed |
| Release Manifest 文件校验 | 1718 files，0 failure |
| EXE File Version | `2.0.0.3` |
| EXE Product Version | `2.0.0rc3` |
| 残留 pytest 进程 | 0 |

## 四项硬保护验证

### Agent Identity

- Agent ID 升级前后均为 `agent-a8c230a7f58d4e7ea312153c3f29fa32`。
- Device ID 升级前后均为 `device-2254aa0b078f42b3a0a1f85e7dff96a9`。
- Identity Status 升级前后均为 `ACTIVE`。

### Device Binding

- Binding Revision 升级前后均为 `2`。
- 授权店铺保持为 `c-store-6639df2982014226`、`PDD-SM`。
- 当前店铺保持未选择，未修改用户或店铺权限。

### Host Control

- Host Control 地址保持 `https://127.0.0.1:18443`。
- Agent Control 协议保持 `2.1`。
- RC3 Runtime 已恢复心跳，最终 Runtime 状态为 `ONLINE`。

### Edge / PDD Profile 与 Session

- 受控成功升级前后的受管 Edge PID 均为 `24912`。
- Profile 引用保持 `browser/profiles/agent-a8c230a7f58d4e7ea312153c3f29fa32-b467ed9eae5a/edge`。
- Profile 根目录和关键会话目录身份指纹保持不变。
- 原有 PDD Session 文件未删除、未清理、未重新初始化。
- 本次未扫码、未登录 PDD、未读取客户消息、未执行发送。

## 受控切换中发现并关闭的问题

升级过程中共有三次安全停止，均发生在安装完成之前或触发了回滚：

1. Windows `File.Replace` 空备份路径被 PowerShell 5.1 转换为非法路径。RC1 文件 Hash 未变化；修复原子替换后继续。
2. 正在运行的 Edge 独占 `BrowserMetrics`，完整 Profile 逐文件 Hash 无法作为在线升级 Gate。改为 Profile 路径、根目录创建标识和关键会话目录身份指纹。
3. 原游标扫描正则会把 `DashTrackerDatabase` 中的 `ack` 误判为 ACK 文件。扫描范围已限制到 Agent 自有的 `runtime/` 和 `events/`，并使用完整文件名边界。

最终切换报告为 `PASSED`，`rollback_performed=false`。

## 产物与证据

- 正式包：`dist/windows-client-v2/rc3/AI-CS-Channel-Agent-2.0.0rc3-windows-x64.zip`
- Runtime 最小差异：`dist/windows-client-v2/rc3/runtime-minimal-diff.json`
- 50 轮稳定性证据：`evidence/channel-agent-rc3-stability.json`
- 原位升级证据：`evidence/channel-agent-rc3-live-upgrade.json`

## 最终状态

`CHANNEL_AGENT_2_0_0RC3_UPGRADE_VALIDATED`
