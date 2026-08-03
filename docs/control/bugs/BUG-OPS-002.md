# BUG-OPS-002 — 正式LAN启动被Windows网卡发现长期阻塞

- 等级：P1
- 模块：OPS / Windows Runtime Start
- 状态：FIXED_VERIFIED
- 发现时间：2026-07-31
- 发现版本：`release/product-reliability-hardening-v1@a6b00c9`

## 问题描述

正式服务安全停止后，`start_ai_customer_service.ps1`进入LAN启动入口，但在任何服务创建运行记录之前停滞；240秒外部执行上限到达。四个标准端口均未启动。

## 原因

启动安全检查与旧状态入口共用`Get-NetAdapter`、`Get-NetIPConfiguration`和`Get-NetIPAddress`。本机Windows网络管理Provider发生长期阻塞，导致启动流程无法进入C/A/B/Admin启动阶段。

## 最小修复

- 生产路径改用.NET `NetworkInterface.GetAllNetworkInterfaces()`枚举Up状态的物理Ethernet/WLAN、IPv4、前缀和默认网关。
- 保留虚拟网卡、VPN、无默认网关、非私有IPv4和多网卡歧义拒绝规则。
- Windows网络类型查询放入隔离Job并设置5秒上限；超时时明确返回Unknown且不修改网络或防火墙。
- VPN风险枚举改用同一.NET来源；防火墙状态读取放入隔离Job并设置5秒上限。
- 原PowerShell cmdlet发现仅作为确定性单测兼容入口保留，不再用于标准启动与状态流程。

## 验证结果

- 当前主机发现唯一物理网卡：`192.168.1.11/24`、默认网关`192.168.1.1`，耗时149ms。
- 网络类型解析为`Private`，耗时453ms。
- LAN、状态性能和Runtime入口回归均通过。
- 失败启动未创建四服务监听，数据库和RAG离线清单保持完整；后续由三轮官方启停复验确认。
