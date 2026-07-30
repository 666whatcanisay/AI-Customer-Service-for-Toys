# BUG-RUNTIME-001：错误状态入口造成 B 假阴性

- 等级：P2
- 模块：Runtime / Windows OPS
- 状态：`CLOSED_OPERATOR_ENTRY`
- 检查版本：`AI-CS@42bafcf6630ccbcd1c2dd1d55cb7d3fe735cb1e2`

## 问题描述

使用 loopback 标准入口检查一个实际以 LAN 模式运行的 B 时，状态脚本探测 `127.0.0.1:5173`，而 B 实际监听 `192.168.1.11:5173`，产生 health 假阴性。

## 原因分析

本次正式 Runtime 的受控身份为 `runtimeMode=standard`、`networkMode=LAN`。最初使用了不适用于 LAN 的 `status_ai_customer_service.ps1`，不是服务或运行记录缺陷。

## 处理方案

保留既有运行代码，统一使用 LAN 运维入口：

```powershell
scripts/windows/status_lan_ai_customer_service.ps1 `
  -ConfigPath .runtime/phase-e/config/green-standard.local.ps1
```

## 验证结果

正确入口连续三轮均识别 B `192.168.1.11:5173`、其余服务 loopback、统一 SHA、standard/LAN 运行身份和 HTTP 200。无需代码修复。
