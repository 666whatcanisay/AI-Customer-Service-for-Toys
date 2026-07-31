# AI-CS Current Requirement Status Summary

> 快照日期：2026-07-31
>
> 唯一需求事实来源：[AI-CS Requirement Registry V1](AI-CS-Requirement-Registry-V1.md)
>
> 当前 Gate：`AI_CS_INTERNAL_PRODUCTION_READY / R003_PILOT_ACCEPTANCE_PENDING`

本文件是状态快照，不是第二份需求台账。

## 1. 状态统计

| 状态 | 数量 | 需求 |
| --- | ---: | --- |
| `DONE` | 7 | R001、R002、R004、R006、R008、R009、R010 |
| `IN_PROGRESS` | 1 | R003 |
| `TODO` | 1 | R005 |
| `BLOCKED` | 1 | R007 |
| `DEPRECATED` | 0 | 无 |
| 合计 | 10 | R001–R010 |

## 2. 当前需求状态

| ID | 名称 | 状态 | 当前事实 | 下一 Gate |
| --- | --- | --- | --- | --- |
| R001 | C商品知识运营中心V2 | `DONE` | 正式基线已包含商品知识结构、模板、状态和知识缺口。 | 不重做结构。 |
| R002 | AI客服反馈沉淀闭环 | `DONE` | B/C/contracts工程闭环已进入正式基线。 | 真实效果转R005。 |
| R003 | C新增店铺/商品无法进入B客服 | `IN_PROGRESS` | R006.1已正式发布，指定PILOT商品已在正式Runtime完成人工发布、启用、B选择和A同商品引用回答。 | 执行完整PILOT业务结果验收后决定是否关闭。 |
| R004 | AI-CS运行版本统一 | `DONE` | 正式目录、Runtime身份和回滚锚点已统一。 | 保持运行基线。 |
| R005 | Customer Feedback Loop真实运行验证 | `TODO` | 尚无真实客服运行后的改善证据。 | R003关闭后开展受控Pilot。 |
| R006 | Pilot Business Data Activation V1 | `DONE` | R006.1已正式发布；R006.2焦点刷新、60秒低频检查、待启用计数和筛选全选已纳入V1.0.0内部生产正式基线并通过回归。 | 保持C唯一Owner，不得混入B可信度判断。 |
| R007 | 网络环境导致客服无法访问5173 | `BLOCKED` | 属公司网络/VLAN/端口策略。 | 网络侧第二终端验收。 |
| R008 | Project Structure Simplification V1 | `DONE` | `AI-CS/`成为正式运行与后续开发目录；Recovery保留回滚。 | 旧Worktree另行归档。 |
| R009 | 商品知识采集模板导入 V1 | `DONE` | 实现、浏览器验收及正式0009能力已进入当前0012运行链，后续迁移未改变R009逻辑或删除数据。 | 保持Import Center和导入边界。 |
| R010 | AI-CS Production Finalization V1 | `DONE` | V1.0.0正式文案、来源正式化、测试入口隔离、contracts 0.5.0、0012及全量回归均完成。 | 以`ai-cs-v1.0.0`作为稳定标签；不把本地保护origin误报为远端发布。 |

## 3. 当前主阻塞

R006实现与正式发布阻塞均已关闭。C保存并裁决`data_source/customer_service_status`，提供`/customer-service/catalog/**`最终投影；B只消费投影。正式只读API和浏览器Smoke证明PILOT+DISABLED记录不会清空其他目录，TEST数据连续可用。

V1.0.0内部生产正式基线位于`release/ai-cs-v1.0.0`，功能正式化提交为`9f2b500dc0d6469a04a6953b7886d65e34412a22`，正式文案补丁为`9911ba67cef330a7a1b4f03f82de227cbee6982d`，防复发测试为`0f230c6f50f8b6162c4e52f3b167053e6592c656`；正式标签为`ai-cs-v1.0.0`，精确SHA从Git与Runtime记录解析。Contracts为0.5.0，数据库为`0012_internal_production_finalization_v1`且完整性正常。四服务正式版本在5173/5174/8000/8011以standard/LAN通过；活动集合内部物理名仍为`test_knowledge_v031`、56 chunks，模型`qwen3.5:9b` ready。

历史初始化Store已按审计规则从TEST正式化为`INITIAL_IMPORT`，当前Store矩阵为`INITIAL_IMPORT + ENABLED=1`、`PILOT + ENABLED=1`；Product状态、activation receipt、发布记录、chunks和embeddings均未删除或重建。浏览器验证Admin正式页面与六模板入口，B已发布商品显示3 chunks/3 citations并保持人工确认、不自动发送/退款/改订单边界。

## 4. 执行顺序

```text
R006 Production Release COMPLETE
  ↓
R006.1 Production Release COMPLETE
  ↓
R006.2 Experience Implementation COMPLETE
  ↓
R010 Production Finalization DONE
  ↓
R003业务结果验收
  ↓
R005真实Pilot验证
```

Prompt、R009导入逻辑、Import Center和B客服核心业务流程未修改。本次正式化和浏览器Smoke不能替代R003全量业务验收或R005真实运行验证；R007继续由网络侧处理。当前`origin`为本地历史保护仓库，没有远端发布声明。
