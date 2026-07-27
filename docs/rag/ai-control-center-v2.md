# AI 控制中心 V2

## 目标

为技术负责人提供一个只读 AI 工作台，汇总已有的 RAG、qwen3.5:9b、评测、Badcase 和反馈分析能力。它只消费已发布的 A API，不创建跨线接口，也不对业务或 AI 配置产生写操作。

## 数据与展示

| 工作台区域 | 来源 | 展示边界 |
| --- | --- | --- |
| AI 概览 | `ai-operations.v1` | 模型配置、知识块、保存评测质量、进程回答量 |
| 评测中心 | `ai-quality-baseline.v1` | 真实评测版本、检查项、CASE 标识和评测器归因；不显示原题/答案/来源正文 |
| 问题分析 | `ai-quality-baseline.v1` | 归因和人工验证/优化建议，`automatic_change_allowed=false` |
| Badcase | `ai-operations.v1` | 四个固定分类；无批准聚合时计数为 `null` |
| 异常状态 | `ai-operations.v1` | 受控原因、外部数据状态和人工下一步 |
| Prompt | `ai-control-center.v1.1` | 当前版本、更新时间、来源和安全预览；只读 |

三个请求独立加载。若任一个请求或严格 schema 校验失败，页面仅显示该区域的错误或“暂无数据”，不会用 fixture、缓存结果或猜测数值替代。

## 运行边界

- 不调用 qwen、不触发评测或反馈分析。
- 不读取客户原文、原始反馈、来源正文、Prompt 正文、密钥或 C 地址。
- 不修改 Prompt、知识、规则、模型、评测、反馈或 C 数据。
- 不将进程内指标、保存测试评测或分类信号表述为生产审计、SLA、员工评价或全量业务质量。

## 实际验证结果

2026-07-27 实际读取三个 A 路由均返回 200；最新保存评测为 `a-t03-v031-live`，结果 19/28。安全标志 `raw_content_exposed=false` 与 `model_or_prompt_changed=false`；Badcase 计数均为 `null`。完整后端回归 80 passed、前端 91 tests passed，真实本地 qwen3.5:9b scoped smoke 通过。
