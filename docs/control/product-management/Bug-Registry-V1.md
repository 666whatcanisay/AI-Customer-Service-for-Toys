# AI-CS Bug Registry V1

| Bug | 等级 | 模块 | 状态 | 结论 |
| --- | --- | --- | --- | --- |
| [BUG-A-001](../bugs/BUG-A-001.md) | P1 | A/Runtime | FIXED_VERIFIED | loopback Ollama 绕过环境代理，正式推理通过 |
| [BUG-A-002](../bugs/BUG-A-002.md) | P1 | A/RAG scope | FIXED_VERIFIED | 不存在商品不再回退到其他商品知识 |
| [BUG-A-003](../bugs/BUG-A-003.md) | P1 | A/回答质量 | FIXED_VERIFIED | 年龄路由与结构化字段证据闸门完成 |
| [BUG-B-001](../bugs/BUG-B-001.md) | P1 | B/C Catalog | OPEN / R006_IMPLEMENTATION_PLAN_READY | 单条异常导致目录整批不可用；禁止临时绕过 |
| [BUG-RUNTIME-001](../bugs/BUG-RUNTIME-001.md) | P2 | OPS | CLOSED_OPERATOR_ENTRY | 使用错误状态入口，不是代码缺陷 |
| [BUG-A-004](../bugs/BUG-A-004.md) | P2 | A/回答体验 | OPEN_DEFERRED | SKU 已明确时仍有泛化确认措辞 |

## 治理规则

发现问题必须先创建 `docs/control/bugs/BUG-*.md`，记录复现、原因、方案和验证，再修改代码。P0/P1 未关闭时不得宣称产品稳定；因边界禁止而无法修复的 P1 必须标记阻塞需求和重新验收范围。
