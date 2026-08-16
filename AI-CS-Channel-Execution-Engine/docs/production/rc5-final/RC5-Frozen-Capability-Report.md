# RC5 Frozen Capability Report

## 冻结结论

以下能力已经通过离线验收，进入 RC5 冻结状态。没有明确缺陷、变更影响分析和完整回归计划时，禁止重构。

| 冻结能力 | 状态 | 重新验收触发条件 |
|---|---|---|
| Provider 统一入口与 Observation 合同 | PASS / FROZEN | 修改字段、幂等键、来源映射或 Provider 路由 |
| ACK / Cursor / 去重 / 断点恢复 | PASS / FROZEN | 修改 ACK 推进条件、游标存储或重试策略 |
| Conversation Buffer | PASS / FROZEN | 修改合并窗口、会话键或顺序规则 |
| Agent Identity | PASS / FROZEN | 修改身份文件、注册、恢复或升级保留逻辑 |
| Device Binding / Store Binding | PASS / FROZEN | 修改绑定协议、revision 或授权店铺校验 |
| Edge Profile / PDD Session 保留 | PASS / FROZEN | 安装、升级、卸载逻辑涉及数据目录 |
| Gateway Contract | PASS / FROZEN | Contract SHA、Schema 或 wire protocol 变化 |
| CustomerContext | PASS / FROZEN | 商品、SKU、订单、物流或客户隔离键变化 |
| AI-CS / RAG 合同 | PASS / FROZEN | Prompt、响应 Schema、引用或风险字段变化 |
| Quality Gate | PASS / FROZEN | 风险阈值、缺知识策略或拦截条件变化 |
| MANUAL_CONFIRM / AUTO_LOW_RISK | PASS / FROZEN | 模式含义、自动允许范围或人工接管变化 |
| Execution 安全门 / Kill Switch | PASS / FROZEN | 权限、店铺、会话、真实发送开关变化 |
| ExecutionPrepared 状态语义 | PASS / FROZEN | 准备、执行、回执三者状态映射变化 |
| Synthetic / Real Receipt 隔离 | PASS / FROZEN | 回执表、Receipt 类型或 UI 展示变化 |
| 多会话 / 多店铺隔离 | PASS / FROZEN | 任何 store_id / conversation_id 分区规则变化 |

## 允许修改的情形

1. 有可复现问题和 Issue 编号。
2. 证明配置无法解决。
3. 先写变更影响和回归范围。
4. 最小修改并补测试。
5. 重新生成候选包、BOM 和受影响 Gate 证据。

## 不得直接修改

- 不得为了适配真实 PDD 重写 Host、AI 或 Execution 核心。
- 不得将 `EXECUTION_PREPARED` 映射为已发送或 Receipt。
- 不得让 AUTO_LOW_RISK 绕过 Quality Gate、店铺绑定或 Kill Switch。
- 不得在升级时清理 Identity、Binding、Profile 或 Session。

