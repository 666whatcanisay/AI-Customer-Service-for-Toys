# BUG-A-001：A 就绪但真实模型调用失败

- 等级：P1
- 模块：A AI 能力层 / Runtime
- 状态：`FIXED_VERIFIED`
- 发现版本：`AI-CS@4edf131cb341993b12a0143b0388d932b29faf84`
- 修复提交：`18a20f70ec5cd4c4da7baef0179cc30db0dbff5a`
- 正式验证版本：`AI-CS@42bafcf6630ccbcd1c2dd1d55cb7d3fe735cb1e2`

## 问题描述

`/api/status` 返回 `ready=true`、`model_configured=true`，但 `/api/chat` 调用本机 Ollama 时返回 HTTP 502，并把技术失败文案暴露给客服。

## 复现步骤

1. 请求 `GET /api/status`，确认服务就绪。
2. 使用正式商品上下文请求 `POST /api/chat`。
3. 观察回答包含“大模型请求失败”，应用日志记录 `HTTP Error 502: Bad Gateway`。
4. 同机直接请求 Ollama 成功，且 A 进程请求未到达 Ollama。

## 原因分析

A 进程继承了系统代理环境；`urllib` 对 loopback Ollama 地址仍使用代理，导致本地请求被代理返回 502。健康接口没有执行真实模型推理，因此仅能证明配置存在，不能覆盖该故障。

## 修复方案

当 Ollama URL 为 loopback 地址时，使用不含代理的 `urllib` opener 发起请求。未更换模型、未修改 Prompt、未修改 RAG 数据。

## 验证结果

- A 全量：`105 passed, 3 skipped`。
- 正式 Runtime 年龄咨询返回 `CONTROLLED_ANSWER`，真实 Ollama 调用成功且无技术失败文案。
- 退款和安全高风险问题分别保持 `TRANSFER_HUMAN`，warnings 含 `SUGGESTION_ONLY`、`AUTO_SEND_DISABLED`。
- 三轮启停和 A 故障模拟恢复后复验通过。
