# AI-CS Product Management Requirement Registry

权威需求台账仍为 [`docs/control/AI-CS-Requirement-Registry-V1.md`](../AI-CS-Requirement-Registry-V1.md)。本文件提供当前产品稳定性视角的索引，不复制或重定义业务需求。

| 需求/任务 | 状态 | 本次关系 | 证据/结论 |
| --- | --- | --- | --- |
| R008 Runtime 收敛 | DONE | 稳定性基线 | 正式目录 `AI-CS`；三轮启停、身份和回滚锚点复验 |
| Runtime Identity Alignment | DONE | 运行前置 | 四服务 `runtimeMode=standard`、`networkMode=LAN` |
| Browser Acceptance Enablement | DONE | 测试能力 | Playwright Chromium 可点击、填表、真实上传文件和截图 |
| R009 商品知识导入 V1 | DONE / PRODUCTION INTEGRATED | C/R009 回归对象 | 0009能力已保留至0012运行链；正式化未修改导入、Merge、审核或Import Center边界 |
| R006 Business Data Activation | DONE / PRODUCTION RELEASED | `BUG-B-001` 的正确修复入口 | 正式Release、0010、C投影/运营控制、B消费和生产Smoke完成；R003业务验收独立跟踪 |
| Product Stabilization & Reliability Sprint V1 | RELEASE GATE PASSED / BUSINESS REGRESSION PENDING | 稳定性任务 | 原唯一P1已完成正式Smoke；B完整日常咨询与R003激活验收仍需执行 |
| R010 AI-CS Production Finalization V1 | DONE / INTERNAL PRODUCTION READY | 正式版本收敛 | V1.0.0文案、INITIAL_IMPORT审计、测试入口隔离、contracts 0.5.0、0012、全量回归与浏览器验收完成；未声明远端发布 |

当前状态总计：`DONE=7`、`IN_PROGRESS=1`、`TODO=1`、`BLOCKED=1`，共10项；R003、R005、R007保持原状态。

## 防重复规则

1. R009 浏览器验收通过不等于 RAG 发布，也不等于 B 可立即消费。
2. Runtime 健康不等于商品目录业务 Gate 通过。
3. `BUG-B-001` 不得重复包装成 B UI 修复；必须引用 R006。
4. 新任务开始前必须核对正式 Runtime SHA、数据库 revision 和数据写入边界。
5. `INITIAL_IMPORT`是历史初始化来源的正式业务标签，不得删除原始来源、导入批次或审计记录，也不得据此重新生成RAG。
6. 本地`ai-cs-v1.0.0`标签和本地保护origin不能作为远端发布证据；远端分发必须另有授权与可核验引用。
