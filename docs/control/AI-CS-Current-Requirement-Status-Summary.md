# AI-CS Current Requirement Status Summary

> 快照日期：2026-07-31
>
> 唯一需求事实来源：[AI-CS Requirement Registry V1](AI-CS-Requirement-Registry-V1.md)
>
> 当前 Gate：`R006_1_IMPLEMENTATION_COMPLETE / R006_1_PRODUCTION_RELEASE_PENDING`

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
| R003 | C新增店铺/商品无法进入B客服 | `IN_PROGRESS` | R006已正式发布；R006.1隔离验收已证明PILOT商品可启用、发布并被B/A使用。 | 发布R006.1后执行正式PILOT完整业务验收。 |
| R004 | AI-CS运行版本统一 | `DONE` | 正式目录、Runtime身份和回滚锚点已统一。 | 保持运行基线。 |
| R005 | Customer Feedback Loop真实运行验证 | `TODO` | 尚无真实客服运行后的改善证据。 | R003关闭后开展受控Pilot。 |
| R006 | Pilot Business Data Activation V1 | `DONE` | 正式0010与C→B投影完成；R006.1实现候选增加AI知识状态、增量发布与批量启用。 | 独立发布R006.1；不得混入R009或B新判断。 |
| R007 | 网络环境导致客服无法访问5173 | `BLOCKED` | 属公司网络/VLAN/端口策略。 | 网络侧第二终端验收。 |
| R008 | Project Structure Simplification V1 | `DONE` | `AI-CS/`成为正式运行与后续开发目录；Recovery保留回滚。 | 旧Worktree另行归档。 |
| R009 | 商品知识采集模板导入 V1 | `DONE` | 实现、浏览器验收及正式0009能力已进入当前0010运行基线。 | 保持Import Center和导入边界。 |

## 3. 当前主阻塞

R006实现与正式发布阻塞均已关闭。C保存并裁决`data_source/customer_service_status`，提供`/customer-service/catalog/**`最终投影；B只消费投影。正式只读API和浏览器Smoke证明PILOT+DISABLED记录不会清空其他目录，TEST数据连续可用。

当前正式Runtime为`release/r006-customer-available-catalog-v1@b7783f7`、数据库0010；`BUG-B-001`状态为`FIXED_VERIFIED_PRODUCTION_SMOKE`。R006.1候选已在隔离0011 Runtime完成发布、启用、B选择和A回答闭环，但尚未部署正式Runtime。

## 4. 执行顺序

```text
R006 Production Release COMPLETE
  ↓
R006.1 Implementation COMPLETE
  ↓ 独立Production Release（未授权执行）
R003业务结果验收
  ↓
R005真实Pilot验证
```

正式Runtime与正式0010数据库在R006.1实现阶段均保持不变；Prompt、R009导入、Import Center和B客服流程未修改。
