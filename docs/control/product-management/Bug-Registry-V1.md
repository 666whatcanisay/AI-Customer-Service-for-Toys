# AI-CS Bug Registry V1

| Bug | 等级 | 模块 | 状态 | 结论 |
| --- | --- | --- | --- | --- |
| [BUG-A-001](../bugs/BUG-A-001.md) | P1 | A/Runtime | FIXED_VERIFIED | loopback Ollama 绕过环境代理，正式推理通过 |
| [BUG-A-002](../bugs/BUG-A-002.md) | P1 | A/RAG scope | FIXED_VERIFIED | 不存在商品不再回退到其他商品知识 |
| [BUG-A-003](../bugs/BUG-A-003.md) | P1 | A/回答质量 | FIXED_VERIFIED | 年龄路由与结构化字段证据闸门完成 |
| [BUG-B-001](../bugs/BUG-B-001.md) | P1 | B/C Catalog | FIXED_VERIFIED_PRODUCTION_SMOKE | 正式0010、C/B API与浏览器目录Smoke通过；完整R003人工激活验收另行执行 |
| [BUG-B-002](../bugs/BUG-B-002.md) | P2 | B/C AI知识状态 | FIXED_VERIFIED_PRODUCTION | B展示C权威发布状态、3条引用和publication receipt，正式浏览器通过 |
| [BUG-C-001](../bugs/BUG-C-001.md) | P1 | C Admin知识审核 | FIXED_VERIFIED_PRODUCTION | 独立审核入口恢复，APPROVED_FOR_ANALYSIS不写R009正式商品字段 |
| [BUG-RUNTIME-001](../bugs/BUG-RUNTIME-001.md) | P2 | OPS | CLOSED_OPERATOR_ENTRY | 使用错误状态入口，不是代码缺陷 |
| [BUG-RUNTIME-002](../bugs/BUG-RUNTIME-002.md) | P1 | OPS/Windows entry | FIXED_VERIFIED | 通用Auto入口、正式配置回退、模式偏好及中文BAT通过正式stop/start/status验收 |
| [BUG-RUNTIME-003](../bugs/BUG-RUNTIME-003.md) | P2 | OPS/PowerShell tests | FIXED_VERIFIED_PRODUCTION | 预期错误流不再中断旧T04夹具，正式OPS三套回归通过 |
| [BUG-RUNTIME-004](../bugs/BUG-RUNTIME-004.md) | P1 | OPS/Admin CORS | FIXED_VERIFIED_PRODUCTION | 仅放行本机Admin 5174，正式浏览器发布闭环通过且未暴露LAN 5174 |
| [BUG-A-004](../bugs/BUG-A-004.md) | P2 | A/回答体验 | OPEN_DEFERRED | SKU 已明确时仍有泛化确认措辞 |

## 治理规则

发现问题必须先创建 `docs/control/bugs/BUG-*.md`，记录复现、原因、方案和验证，再修改代码。P0/P1 未关闭时不得宣称产品稳定；因边界禁止而无法修复的 P1 必须标记阻塞需求和重新验收范围。
