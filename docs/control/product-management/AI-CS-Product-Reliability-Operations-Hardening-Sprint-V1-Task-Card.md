# AI-CS Product Reliability & Operations Hardening Sprint V1 Task Card

## 目标

在`AI-CS@86a66cc`既有业务能力上完成可复现的运行、客服、运营、AI、数据与运维稳定性验证；发现问题先登记、再最小修复并回归，不新增业务能力。

## 范围与Owner

- B/QA：客服咨询、上下文隔离、空态/异常态与Catalog四态。
- C/QA：商品、知识、AI问题中心和R009隔离数据库回归。
- A/QA：知识回答、无知识拒答、跨商品隔离和高风险安全边界。
- OPS：Runtime身份、状态脚本耗时、三轮启停和恢复证据。
- Data/Control：只读关系、一致性、SQLite健康检查及Bug/测试/发布文档。

不包含：新业务、ERP/API、新模板、新Agent、新数据库领域、PostgreSQL、R006架构、R009导入逻辑、Prompt/模型/RAG业务规则变更。

## 成功标准

1. 四服务同一受管SHA，`standard/LAN`，health通过。
2. B/C/A指定场景有真实或明确隔离的自动化证据；Mock不得替代正式成功链路。
3. R009只在隔离SQLite和隔离端口执行，正式数据库零写入。
4. 数据质量和数据库健康脚本只读、可复现、失败码明确。
5. status脚本耗时根因有证据，修复后失败原因明确且不改变业务。
6. 三轮stop/start/status后四服务、数据库、RAG和模型恢复。
7. 所有Bug先登记，P0/P1关闭或明确阻塞；报告只记录已验证事实。

## 风险与停止条件

- Runtime身份不一致、未知PID、数据库完整性失败、RAG数量异常或正式业务写入风险：立即停止。
- 正式R009、状态切换、反馈或知识发布写操作禁止通过测试触发。
- 任何需修改R006/R009架构、Prompt、模型或数据库结构的问题转为独立任务，不在本Sprint扩大范围。

## 验收Gate

- 初始Gate：`RELIABILITY_SPRINT_READY`
- 目标Gate：`AI_CS_PRODUCT_RELIABILITY_HARDENED_V1`
- 基线：`release/r006-customer-available-catalog-consumer-v1@86a66cc425df26141745d4af608921021c9036a4`
- 分支：`codex/product-reliability-hardening-v1`
