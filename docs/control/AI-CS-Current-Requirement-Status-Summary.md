# AI-CS Current Requirement Status Summary

> 快照日期：2026-07-31
>
> 唯一需求事实来源：[AI-CS Requirement Registry V1](AI-CS-Requirement-Registry-V1.md)
>
> 当前 Gate：`R006_IMPLEMENTATION_PLAN_READY`

本文件是状态快照，不是第二份需求台账。

## 1. 状态统计

| 状态 | 数量 | 需求 |
| --- | ---: | --- |
| `DONE` | 5 | R001、R002、R004、R008、R009 |
| `IN_PROGRESS` | 2 | R003、R006 |
| `TODO` | 1 | R005 |
| `BLOCKED` | 1 | R007 |
| `DEPRECATED` | 0 | 无 |
| 合计 | 9 | R001–R009 |

## 2. 当前需求状态

| ID | 名称 | 状态 | 当前事实 | 下一 Gate |
| --- | --- | --- | --- | --- |
| R001 | C商品知识运营中心V2 | `DONE` | 正式基线已包含商品知识结构、模板、状态和知识缺口。 | 不重做结构。 |
| R002 | AI客服反馈沉淀闭环 | `DONE` | B/C/contracts工程闭环已进入正式基线。 | 真实效果转R005。 |
| R003 | C新增店铺/商品无法进入B客服 | `IN_PROGRESS` | `BUG-B-001`已定位到C最终投影缺失；R006实施计划就绪。 | R006实现并完成业务验收。 |
| R004 | AI-CS运行版本统一 | `DONE` | 正式目录、Runtime身份和回滚锚点已统一。 | 保持运行基线。 |
| R005 | Customer Feedback Loop真实运行验证 | `TODO` | 尚无真实客服运行后的改善证据。 | R003关闭后开展受控Pilot。 |
| R006 | Pilot Business Data Activation V1 | `IN_PROGRESS` | 来源映射、Customer Available状态、投影、receipt和B消费计划已冻结；尚无代码。 | contracts 0.3.0 → C → B → QA。 |
| R007 | 网络环境导致客服无法访问5173 | `BLOCKED` | 属公司网络/VLAN/端口策略。 | 网络侧第二终端验收。 |
| R008 | Project Structure Simplification V1 | `DONE` | `AI-CS/`成为正式运行与后续开发目录；Recovery保留回滚。 | 旧Worktree另行归档。 |
| R009 | 商品知识采集模板导入 V1 | `DONE` | 实现及隔离0009浏览器验收完成。 | 正式发布独立执行，不与R006混入。 |

## 3. 当前主阻塞

正式 C `/test-catalog/stores` 同时返回历史TEST Store和C运营Store；B用旧字段检查整批，只要一条不兼容即清空全部目录。R006计划已明确由C保存和裁决`data_source/customer_service_status`并提供`/customer-service/catalog/**`最终投影，B只消费投影。

此前IV11-B01/B02已在计划层关闭：

- `IMPORTED_TEST_ONLY+0.3.1-test → TEST+ENABLED`；
- `MANUAL_CREATED+c-operation-store.v1 → PILOT+DISABLED`；
- 未知来源隔离；
- 状态PUT、Idempotency-Key、changed true/false、receipt查询和错误码已明确。

这些是设计证据，不是代码或运行证据。`BUG-B-001`仍为OPEN。

## 4. 执行顺序

```text
R006 Implementation Plan READY
  ↓
contracts 0.3.0 additive schema
  ↓
0010 migration + C status/receipt persistence
  ↓
C Customer Available Catalog Projection
  ↓
C最小运营控制入口
  ↓
B Consumer契约切换
  ↓
隔离QA与B-001～B-006浏览器验收
  ↓
独立Production Release
  ↓
R003业务结果验收
  ↓
R005真实Pilot验证
```

正式Runtime、正式0008数据库、A、RAG、Prompt和R009在当前计划阶段均保持不变。
