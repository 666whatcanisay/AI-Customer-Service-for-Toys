# BUG-OPS-001 — 正式LAN状态脚本被Windows网卡发现长期阻塞

- 等级：P1
- 模块：OPS / Windows Runtime Status
- 状态：FIXED_VERIFIED
- 发现时间：2026-07-31
- 发现版本：`AI-CS@86a66cc`

## 问题描述

正式四服务健康运行时，`status_ai_customer_service.ps1`在选择LAN模式后超过180秒仍不返回。用户无法及时判断PID、SHA、健康状态和数据库revision。

## 复现步骤

1. 保持正式LAN Runtime运行。
2. 执行`status_ai_customer_service.ps1`。
3. 通用入口输出已选择LAN Runtime后，脚本停滞；180秒外部计时上限到达仍无结果。

## 原因

LAN状态入口每次都调用`Get-NetAdapter`、`Get-NetIPConfiguration`、`Get-NetIPAddress`和`Get-NetConnectionProfile`重新发现网络。当前Windows主机上的网络管理调用发生长期阻塞，而服务受管记录本身已经包含经过启动流程确认的LAN地址、仓库和网络模式。

## 最小修复

- 状态检查优先读取并校验`customer-web.json`受管记录，不再为日常状态查询重复扫描网卡。
- 仅当记录缺失、损坏、仓库不一致或地址不可信时，回退原动态网络发现。
- C/A/B/Admin四个HTTP健康检查并行发起，单项超时3秒。
- HTTP失败显示具体原因；记录来源明确显示为`MANAGED_RECORD`或`DYNAMIC_DISCOVERY`。
- 动态网卡、防火墙和网关详情仍由专用诊断脚本承担，启动安全检查保持不变。

## 验证结果

- 修复前：正式状态命令超过180秒，外部计时终止。
- 修复后：相同正式Runtime完整输出耗时3114ms，exit code 0。
- 四服务均显示RUNNING、`86a66cc425df`、`runtimeMode=standard`、`networkMode=LAN`、源码CLEAN。
- 新增OPS性能测试，并保留LAN选择、运行入口与受管PID既有回归测试。
