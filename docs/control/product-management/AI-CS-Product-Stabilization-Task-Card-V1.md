# AI-CS Product Stabilization & Reliability Sprint V1 Task Card

任务：AI-CS Product Stabilization & Reliability Sprint V1

目标：在不扩展业务范围、不改变 R006 接口边界、不修改模型或 Prompt 的前提下，验证并修复现有 B/C/A/R009/Runtime 的稳定性问题，沉淀可复用 E2E 与产品管理流程，形成可复现的稳定候选版本。

范围：

- B 客服日常咨询、错误态、多 SKU、商品切换和连续对话；
- C 商品管理、商品知识、Import Center、R009 导入和 AI 问题中心；
- R009 正常、异常、幂等和 100 行性能回归；
- 正式 Runtime 身份、三轮启停、A/C 故障降级与数据库保护；
- AI 有知识、无知识和高风险建议质量；
- Bug 台账、回归测试、E2E、Release Notes 与交接。

不包含：ERP、外部系统同步、金蝶、拼多多自动同步、新业务模块、新 Excel 模板、新 Agent、R006 修改、自动客服发送、自动退款、订单写入、Prompt/模型/RAG 数据修改。

所有者：Control 负责 Gate 与报告；B/C/A/OPS/QA 按现有目录所有权提供实现与证据。本任务不创建或委派新 Agent，由总控串行执行。

成功标准：

1. 正式 Runtime 身份、健康、数据库、Chroma 和 Ollama 基线可追溯；
2. 指定 B/C/R009/AI 场景均有真实浏览器或明确的受控测试证据；
3. 所有发现先登记 Bug，再修复；每个修复都有复现与回归；
4. 三轮 stop/start/status 和故障恢复不丢失数据、不残留未知进程；
5. E2E 与产品管理文档可供后续复用；
6. 正式数据、知识、向量、日志、模型和密钥不进入 Git。

风险与缓解：

- 正式服务启停可能影响 Pilot → 先确认身份、静默窗口、在线备份和回滚锚点，再执行短时受控循环；
- 浏览器测试可能写入业务数据 → 写操作优先在隔离 0009 数据库执行，正式库只做只读或明确可回滚的既有流程；
- 故障模拟可能遗留停服 → 只使用受管脚本和已验证 PID，模拟后立即恢复并复核四端口；
- AI 质量具有非确定性 → 记录问题、来源、action、风险和延迟，不自动改 Prompt、规则或知识。

停止条件：运行身份不一致且无法安全回滚、数据库备份失败、发现未知监听 PID、正式服务存在无法确认的人工会话，或出现 P0 数据损坏风险。

验收：以 Runtime 报告、浏览器截图、数据库只读核对、自动测试结果、Bug 记录、修复提交和最终 Gate 为证据。完成 Gate 为 `AI_CS_PRODUCT_STABLE_V1_READY`；证据不足时必须返回 `CONDITIONAL PASS` 或 `BLOCKED`。
