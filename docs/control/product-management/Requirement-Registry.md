# AI-CS Product Management Requirement Registry

权威需求台账仍为 [`docs/control/AI-CS-Requirement-Registry-V1.md`](../AI-CS-Requirement-Registry-V1.md)。本文件提供当前产品稳定性视角的索引，不复制或重定义业务需求。

| 需求/任务 | 状态 | 本次关系 | 证据/结论 |
| --- | --- | --- | --- |
| R008 Runtime 收敛 | DONE | 稳定性基线 | 正式目录 `AI-CS`；三轮启停、身份和回滚锚点复验 |
| Runtime Identity Alignment | DONE | 运行前置 | 四服务 `runtimeMode=standard`、`networkMode=LAN` |
| Browser Acceptance Enablement | DONE | 测试能力 | Playwright Chromium 可点击、填表、真实上传文件和截图 |
| R009 商品知识导入 V1 | IMPLEMENTED / SCHEMA DEPLOYED | C/R009 回归对象 | 0009已随冻结迁移链进入正式库，业务逻辑未修改，正式导入数据仍为0；完整生产验收另立任务 |
| R006 Business Data Activation | DONE / PRODUCTION RELEASED | `BUG-B-001` 的正确修复入口 | 正式Release、0010、C投影/运营控制、B消费和生产Smoke完成；R003业务验收独立跟踪 |
| Product Stabilization & Reliability Sprint V1 | RELEASE GATE PASSED / BUSINESS REGRESSION PENDING | 稳定性任务 | 原唯一P1已完成正式Smoke；B完整日常咨询与R003激活验收仍需执行 |

## 防重复规则

1. R009 浏览器验收通过不等于 RAG 发布，也不等于 B 可立即消费。
2. Runtime 健康不等于商品目录业务 Gate 通过。
3. `BUG-B-001` 不得重复包装成 B UI 修复；必须引用 R006。
4. 新任务开始前必须核对正式 Runtime SHA、数据库 revision 和数据写入边界。
