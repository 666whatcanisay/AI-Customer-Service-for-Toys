# AI-CS Production Finalization V1 Task Card

- 任务 ID：`R010-INTERNAL-PRODUCTION-FINALIZATION-V1`
- 发布分支：`release/ai-cs-v1.0.0`
- 基线：`feature/r006-2-customer-experience-polish-v1@c1baad8dc6d8728d6c777967d4efbf9c7bb76312`
- 目标：将已完成的 R006、R006.1、R006.2 收敛为可复现的 `AI-CS V1.0.0` 内部生产版本。

## 范围

- B、C Admin 的用户可见文案正式化，保留人工确认、不自动发送、不自动退款、不修改订单。
- 将经既有 `IMPORTED_TEST_ONLY + 0.3.1-test` 识别的历史初始化店铺投影为 `INITIAL_IMPORT`，保留原始来源、导入包、收据与迁移审计。
- 隔离测试数据包的运营入口；测试代码、夹具、浏览器证据和回归数据继续保留。
- 通过独立、可逆的 `0012_internal_production_finalization_v1` 迁移、完整回归、数据备份和标准 Runtime 重启完成发布。

## 不包含

- 不改 R006 / R006.1 / R006.2 的客服启用、知识发布、RAG 或 B 消费规则。
- 不改 A 回答逻辑、Prompt、模型、RAG 发布机制、Import Center 的六模板定位或 Windows 启动脚本。
- 不删除业务数据、商品知识、RAG chunk、embedding、activation receipt、migration 历史、测试夹具或测试包。

## 兼容冻结

- C 继续是客服目录和数据来源的唯一 Owner；B 继续只消费 C 的最终投影。
- `INITIAL_IMPORT` 是 `TEST` 的加性、正式化来源值；旧 `TEST` 仍可被读取和审计。
- 迁移只更新符合既有初始化证据的 Store 当前来源标签；Product/SKU 继续继承 Store 来源。
- 历史 activation receipt 的 `data_source=TEST` 不回写，作为不可变审计证据。

## 成功标准

1. 运营和客服可见页面不显示“测试环境、内部验证、禁止真实客户使用、测试数据提示、TEST、PILOT、DEMO”。
2. 所有安全边界仍可见；用户不能触发自动发送、退款或订单修改。
3. `0012` 在隔离 SQLite 中完成 upgrade → downgrade → upgrade，且来源审计、商品状态、发布状态和 receipt 均被保留。
4. B、C、A、contracts 测试及构建通过；标准启动、状态和停止入口保持不变。
5. 正式数据库完成在线备份与离线回滚快照，完整性检查通过；发布后四服务运行同一 SHA，数据库为 `0012`，活动集合和 chunk 数不减少。

## 风险与缓解

- 新来源枚举可能被旧 B 拒绝：先升级 contracts/C/B，再执行正式迁移和 Runtime 重启。
- SQLite 数据迁移风险：先在线备份、离线快照和隔离往返；迁移失败立即恢复备份，不使用破坏性 downgrade。
- 正式化文案误弱化安全边界：浏览器回归逐页核对人工确认和禁用自动业务动作。

## Gate

当前：`AI_CS_INTERNAL_PRODUCTION_READY`。

## 完成证据

- 正式化主体提交：`9f2b500dc0d6469a04a6953b7886d65e34412a22`。
- P2 文案补丁：`9911ba67cef330a7a1b4f03f82de227cbee6982d`，详见 `BUG-B-003`。
- 防复发测试：`0f230c6f50f8b6162c4e52f3b167053e6592c656`。
- 正式版本引用：`ai-cs-v1.0.0`。
- Contracts：`0.5.0`；数据库：`0012_internal_production_finalization_v1`，integrity check 为 `ok`。
- 四服务标准/LAN Runtime、模型 ready、活动集合 56 chunks 均已验证。
- A/B/C/Admin/contracts 全量或专项测试、类型检查与构建通过。
- Admin 正式页面、六模板、B 商品选择、PUBLISHED 状态、3 条同商品引用和安全边界已完成 Playwright 验收。
- 数据库与 RAG 在线/离线快照、SHA256 与回滚路径已记录在《AI-CS Production Finalization Report V1》。

最终报告：[AI-CS-Production-Finalization-Report-V1.md](../AI-CS-Production-Finalization-Report-V1.md)
