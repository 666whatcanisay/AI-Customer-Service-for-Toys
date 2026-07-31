# AI-CS Current Requirement Status Summary

> 快照日期：2026-07-31
>
> 唯一需求事实来源：[AI-CS Requirement Registry V1](AI-CS-Requirement-Registry-V1.md)
>
> 当前 Gate：`R006_IMPLEMENTATION_COMPLETE / PRODUCTION_RELEASE_PENDING`

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
| R003 | C新增店铺/商品无法进入B客服 | `IN_PROGRESS` | R006候选实现与隔离浏览器验收通过，PILOT启用后B可见。 | 独立正式发布后执行真实业务验收。 |
| R004 | AI-CS运行版本统一 | `DONE` | 正式目录、Runtime身份和回滚锚点已统一。 | 保持运行基线。 |
| R005 | Customer Feedback Loop真实运行验证 | `TODO` | 尚无真实客服运行后的改善证据。 | R003关闭后开展受控Pilot。 |
| R006 | Pilot Business Data Activation V1 | `DONE` | contracts 0.3.0、0010、C投影/控制、B消费和隔离E2E完成。 | 独立Production Release，不与R003/R005混跑。 |
| R007 | 网络环境导致客服无法访问5173 | `BLOCKED` | 属公司网络/VLAN/端口策略。 | 网络侧第二终端验收。 |
| R008 | Project Structure Simplification V1 | `DONE` | `AI-CS/`成为正式运行与后续开发目录；Recovery保留回滚。 | 旧Worktree另行归档。 |
| R009 | 商品知识采集模板导入 V1 | `DONE` | 实现及隔离0009浏览器验收完成。 | 正式发布独立执行，不与R006混入。 |

## 3. 当前主阻塞

R006实现阻塞已关闭。候选代码由C保存并裁决`data_source/customer_service_status`，提供`/customer-service/catalog/**`最终投影；B只消费投影。隔离浏览器已证明单条异常不会清空其他目录、TEST数据连续可用、PILOT需人工启用、Store停用不改Product保存状态且receipt可追溯。

当前剩余 Gate 是独立Production Release：正式`AI-CS@42bafcf/0008`尚未合入候选或执行0010，因此`BUG-B-001`状态为`FIXED_VERIFIED_CANDIDATE / PRODUCTION_RELEASE_PENDING`，R003仍等待正式业务验收。

## 4. 执行顺序

```text
R006 Implementation COMPLETE
  ↓
独立Production Release
  ↓
R003业务结果验收
  ↓
R005真实Pilot验证
```

正式Runtime、正式0008数据库、A、RAG、Prompt和R009在本次实现阶段均保持不变。
