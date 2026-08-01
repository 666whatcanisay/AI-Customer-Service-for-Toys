# AI-CS Bug Registry V1

## AI-CS V1.0.0 正式化新增记录

| Bug | 等级 | 模块 | 状态 | 结论 |
| --- | --- | --- | --- | --- |
| [BUG-B-003](../bugs/BUG-B-003.md) | P2 | B 客服工作台文案 | FIXED_VERIFIED | 移除残留“测试工作台”身份文案，安全边界保持不变；B 全量测试、类型检查、构建和浏览器回归通过。 |

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
| [BUG-OPS-003](../bugs/BUG-OPS-003.md) | P1 | OPS/Windows status | FIXED_VERIFIED | 有界进程元数据查询替代无界 CIM；正式四服务状态约3秒完整返回 |
| [BUG-OPS-004](../bugs/BUG-OPS-004.md) | P1 | OPS/Windows stop | FIXED_VERIFIED | 保持严格身份校验并有界重试；任何运行记录或标准端口残留均返回失败 |
| [BUG-OPS-005](../bugs/BUG-OPS-005.md) | P1 | OPS/Windows BAT | FIXED_VERIFIED | `scripts/windows/.gitattributes` 强制BAT使用CRLF；真实cmd.exe状态入口退出0 |
| [BUG-A-004](../bugs/BUG-A-004.md) | P2 | A/回答体验 | OPEN_DEFERRED | SKU 已明确时仍有泛化确认措辞 |

## 治理规则

发现问题必须先创建 `docs/control/bugs/BUG-*.md`，记录复现、原因、方案和验证，再修改代码。P0/P1 未关闭时不得宣称产品稳定；因边界禁止而无法修复的 P1 必须标记阻塞需求和重新验收范围。
