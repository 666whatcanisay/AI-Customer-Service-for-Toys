# AI-CS Product Management Requirement Registry

权威需求台账仍为 [`docs/control/AI-CS-Requirement-Registry-V1.md`](../AI-CS-Requirement-Registry-V1.md)。本文件提供当前产品稳定性视角的索引，不复制或重定义业务需求。

| 需求/任务 | 状态 | 本次关系 | 证据/结论 |
| --- | --- | --- | --- |
| R008 Runtime 收敛 | DONE | 稳定性基线 | 正式目录 `AI-CS`；三轮启停、身份和回滚锚点复验 |
| Runtime Identity Alignment | DONE | 运行前置 | 四服务 `runtimeMode=standard`、`networkMode=LAN` |
| Browser Acceptance Enablement | DONE | 测试能力 | Playwright Chromium 可点击、填表、真实上传文件和截图 |
| R009 商品知识导入 V1 | IMPLEMENTED / RC ACCEPTED | C/R009 回归对象 | 隔离 0009 浏览器闭环通过；尚未部署正式 0008 Runtime |
| R006 Business Data Activation | DONE / IMPLEMENTATION COMPLETE | `BUG-B-001` 的正确修复入口 | C最终投影、运营控制、B消费、0010和隔离E2E完成；正式发布另立任务 |
| Product Stabilization & Reliability Sprint V1 | CANDIDATE READY / RELEASE PENDING | 当前任务 | 原唯一P1已在R006候选修复；正式Runtime仍待独立发布 |

## 防重复规则

1. R009 浏览器验收通过不等于 RAG 发布，也不等于 B 可立即消费。
2. Runtime 健康不等于商品目录业务 Gate 通过。
3. `BUG-B-001` 不得重复包装成 B UI 修复；必须引用 R006。
4. 新任务开始前必须核对正式 Runtime SHA、数据库 revision 和数据写入边界。
