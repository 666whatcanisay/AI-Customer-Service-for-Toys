# AI-CS Pilot Baseline Inventory Report V1

> 盘点日期：2026-07-29
>
> 盘点方式：只读 Git、文件边界、contracts 与端口核验
>
> Phase 0 Gate：`BASELINE_INVENTORY_CONFIRMED`

## 1. 盘点结论

R001、R002 和 C 店铺/商品运营能力已完成，但盘点时分散在不同
Worktree、不同提交和 C 的混合脏工作区中。标准端口 5173、5174、8000、
8011 均未监听，因此可以建立隔离 Recovery 工作树而不停止未知进程。

## 2. 盘点时的真实代码来源

| 角色 | 目录 | 分支 / SHA | 状态 | 实际能力 |
| --- | --- | --- | --- | --- |
| develop | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-develop-admin-ui-hotfix-v1` | `develop` / `671c9a293f1e5e0f462522ad2c7e114c7919c388` | clean | 共同恢复起点，contracts 0.1.0 |
| Control | `C:\Users\EDY\Documents\Codex\2026-07-21\666whatcanisay-ai-customer-service-for-toys` | `codex/agent-system-foundation-v1` / `e2489ab...` | dirty | Requirement Registry 与控制文档 |
| A | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-rag-core` | `agent/ai-control-center-ui-v1` / `2584b460...` | dirty | A 产品投影来源提交 `058eb41`；contracts 0.1.1 |
| B | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-user-client` | `codex/customer-workbench-v2-product` / `5e2b553...` | dirty | 既有 B 产品化分支；不作为 Feedback Loop 的真实来源 |
| C 混合工作区 | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-platform-center` | `codex/product-knowledge-operation-center-v1` / `671c9a293...` | dirty | C商品知识V2、店铺/商品运营、Feedback C、Feedback B、contracts 0.2.0 与临时输出混合 |

## 3. 正式能力与临时内容

正式归档范围：

- A：产品控制投影 Provider、schema model 与测试。
- C：商品知识、资料识别、知识模板、知识缺口、店铺/商品运营。
- contracts：原始 0.1.0 schema、A 0.1.1 投影 schema、Feedback 0.2.0 schema 与兼容说明。
- Feedback Loop：C 事件权威保存/问题中心/知识任务，以及 B 的采用行为事件与反馈关联。
- Control：需求台账、盘点、恢复执行、运行身份与回滚记录。

未归档内容：

- `outputs/**`、日志、运行记录、数据库、向量库、依赖、构建产物。
- A 分支上的整分支 UI/文档组合；只抽取已批准的 Provider 提交范围。
- B 产品化分支的无关 UI 提交。
- Business Data Activation、Master Data、ERP、PostgreSQL、RBAC、Answer Trace、模型或 Prompt 变更。

## 4. Recovery 起点

- 新工作树：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-pilot-baseline-recovery-v1`
- 分支：`control/pilot-baseline-recovery-v1`
- 基础提交：`671c9a293f1e5e0f462522ad2c7e114c7919c388`
- 原则：只从已识别来源按所有权选择性归档；未使用 `git add .`。

最终结论：`BASELINE_INVENTORY_CONFIRMED`
