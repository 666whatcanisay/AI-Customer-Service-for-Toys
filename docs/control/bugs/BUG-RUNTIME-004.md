# BUG-RUNTIME-004 — LAN Runtime遗漏本机Admin的CORS Origin

- 等级：P1（发布阻塞）
- 模块：Windows OPS / Admin与C、A浏览器连接
- 状态：FIXED_VERIFIED_PRODUCTION
- 发现时间：2026-07-31

## 问题描述

R006.1正式浏览器Smoke中，`5174`页面可打开，C `8011`与A `8000`均健康，但Admin显示“无法连接运营平台”。浏览器请求被CORS拦截，导致运营无法查看商品知识状态、发布AI知识或启用客服。

## 复现步骤

1. 使用标准LAN Runtime启动四服务。
2. 打开`http://127.0.0.1:5174/knowledge-center`。
3. 页面可加载，但商品知识请求失败；对C发送`Origin: http://127.0.0.1:5174`时响应缺少`Access-Control-Allow-Origin`。

## 原因分析

`Get-LanCorsAllowedOrigins`只生成B的LAN/loopback `5173` Origin。Admin仍被安全地限制在本机`5174`，但它直连C和A，因此C/A也必须显式允许本机Admin Origin。该问题不涉及业务逻辑、数据库或对外端口开放。

## 修复原则

- 仅向LAN Runtime的C/A CORS配置增加`127.0.0.1:5174`和`localhost:5174`。
- 不增加通配符，不增加LAN地址的5174，不改变Admin loopback-only边界。
- 增加OPS断言，证明5173 LAN入口与5174本机运营入口均存在，且5174没有被暴露为LAN Origin。

## 修复验证

- `Test-OpsLanMode.ps1`：PASS，明确验证B的LAN Origin、本机Admin两个Origin及5174未暴露到LAN地址。
- `Test-OpsRuntimeFix2.ps1`：PASS，标准启动、active collection检查和失败清理边界未回归。
- 正式Release重启后，`http://127.0.0.1:5174/knowledge-center`可读取C/A并完成发布、启用和状态刷新；LAN地址的5174仍未被加入允许Origin。
