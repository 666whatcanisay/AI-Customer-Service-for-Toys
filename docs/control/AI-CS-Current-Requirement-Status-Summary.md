# AI-CS Current Requirement Status Summary

> 快照日期：2026-07-31
>
> 唯一需求事实来源：[AI-CS Requirement Registry V1](AI-CS-Requirement-Registry-V1.md)
>
> 当前 Gate：`R006_1_PRODUCTION_RELEASE_COMPLETE / R003_PILOT_ACCEPTANCE_PENDING`

本文件是状态快照，不是第二份需求台账。

## 1. 状态统计

| 状态 | 数量 | 需求 |
| --- | ---: | --- |
| `DONE` | 6 | R001、R002、R004、R006、R008、R009 |
| `IN_PROGRESS` | 1 | R003 |
| `TODO` | 1 | R005 |
| `BLOCKED` | 1 | R007 |
| `DEPRECATED` | 0 | 无 |
| 合计 | 9 | R001–R009 |

## 2. 当前需求状态

| ID | 名称 | 状态 | 当前事实 | 下一 Gate |
| --- | --- | --- | --- | --- |
| R001 | C商品知识运营中心V2 | `DONE` | 正式基线已包含商品知识结构、模板、状态和知识缺口。 | 不重做结构。 |
| R002 | AI客服反馈沉淀闭环 | `DONE` | B/C/contracts工程闭环已进入正式基线。 | 真实效果转R005。 |
| R003 | C新增店铺/商品无法进入B客服 | `IN_PROGRESS` | R006.1已正式发布，指定PILOT商品已在正式Runtime完成人工发布、启用、B选择和A同商品引用回答。 | 执行完整PILOT业务结果验收后决定是否关闭。 |
| R004 | AI-CS运行版本统一 | `DONE` | 正式目录、Runtime身份和回滚锚点已统一。 | 保持运行基线。 |
| R005 | Customer Feedback Loop真实运行验证 | `TODO` | 尚无真实客服运行后的改善证据。 | R003关闭后开展受控Pilot。 |
| R006 | Pilot Business Data Activation V1 | `DONE` | R006.1已正式发布：0011、AI知识状态、增量发布、publication receipt、批量启用和B真实状态展示均进入正式Runtime。 | 保持C唯一Owner；不得混入B可信度判断。 |
| R007 | 网络环境导致客服无法访问5173 | `BLOCKED` | 属公司网络/VLAN/端口策略。 | 网络侧第二终端验收。 |
| R008 | Project Structure Simplification V1 | `DONE` | `AI-CS/`成为正式运行与后续开发目录；Recovery保留回滚。 | 旧Worktree另行归档。 |
| R009 | 商品知识采集模板导入 V1 | `DONE` | 实现、浏览器验收及正式0009能力已进入当前0010运行基线。 | 保持Import Center和导入边界。 |

## 3. 当前主阻塞

R006实现与正式发布阻塞均已关闭。C保存并裁决`data_source/customer_service_status`，提供`/customer-service/catalog/**`最终投影；B只消费投影。正式只读API和浏览器Smoke证明PILOT+DISABLED记录不会清空其他目录，TEST数据连续可用。

当前正式Runtime为`release/r006-1-knowledge-activation-v1`，Release代码SHA为`55ca6eb`，数据库为`0011_product_knowledge_publishing_v1`，活动集合为`test_knowledge_v031`、50 chunks。`BUG-B-002`、`BUG-RUNTIME-003`、`BUG-RUNTIME-004`和`BUG-C-001`均已完成正式回归。指定商品在正式浏览器Smoke中达到`APPROVED + ENABLED + PUBLISHED`，B可选且A返回3条同商品来源。

## 4. 执行顺序

```text
R006 Production Release COMPLETE
  ↓
R006.1 Production Release COMPLETE
  ↓
R003业务结果验收
  ↓
R005真实Pilot验证
```

Prompt、R009导入逻辑、Import Center和B客服业务流程未修改。本次正式Smoke不能替代R003全量Pilot验收或R005真实运行验证。
