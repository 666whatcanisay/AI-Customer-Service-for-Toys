# BUG-OPS-003 — Windows 状态检查被进程元数据查询阻塞

- 等级：P1
- 模块：OPS / Windows Runtime
- 状态：FIXED_VERIFIED
- 发现时间：2026-08-01

## 现象

四服务 HTTP 均健康时，`status_ai_customer_service.ps1` 可在输出 C/A/B 后长时间停住，Admin 状态无法及时返回；历史观察超过 90 秒。

## 原因

公共运行库使用无超时的 `Get-CimInstance Win32_Process` 读取进程和父子关系。在当前 Windows WMI/CIM 状态下，该调用可能长时间阻塞；状态脚本还会重复读取 Admin 记录，放大等待。

## 修复

- 改用带 `EnumerationOptions.Timeout` 的 `System.Management.ManagementObjectSearcher`。
- 单 PID 查询默认上限 1500ms，全量父子快照默认上限 2000ms。
- Local/LAN 状态入口复用已取得的 Admin 状态，不重复查询。
- 保留查询失败时的安全失败语义，不凭端口强杀或伪造健康。

## 验证

- `Test-OpsStatusPerformance.ps1` 覆盖进程元数据时间界限，并禁止重新出现无界 `Get-CimInstance Win32_Process`。
- 正式运行记录只读状态检查：四服务完整输出，约 3 秒结束，退出码 0。
- 全量 10 个 Windows OPS 脚本测试通过。
