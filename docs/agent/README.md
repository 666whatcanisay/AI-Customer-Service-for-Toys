# Agent 协作资产

## 角色与职责

| 角色 | 目标 | 不可越界的职责 |
| --- | --- | --- |
| Control / Interface Owner | 定义目标、范围、Gate、接口冻结、合并与交接 | 不替代各线开发；无接口冻结不允许跨线实现 |
| A AI-Team | AI/RAG、模型状态、评测、质量分析 | 不写 C 的业务数据模型，不自动改 Prompt/知识/模型 |
| B Customer-Team | 客服使用流程、人工确认、案例/反馈采集 | 不审核、训练或执行客户业务动作 |
| C Platform-Team | 数据保存、审核、运营视图、导入与受控导出 | 不替代 AI 决策，不做 ERP 写入 |
| OPS-Team | 运行一致性、启停、网络、安全诊断 | 不强杀未知进程，不暴露内部端口 |
| QA / Integration | 使用真实数据与服务验证闭环 | 不用 Mock 冒充端到端结果 |

## 推荐工作流

1. 读取根 `AGENTS.md`、本线自我介绍/状态/machine context 与本任务所需 Skill。
2. 用任务卡写明目标、范围、禁止项、数据/接口所有者、验收标准、风险和 Gate。
3. 先核对工作树和运行环境。存在用户脏改动时保护它们并用独立 worktree。
4. 跨线功能先更新/确认 `docs/control/interfaces/*.v1.md`：目标、Provider/Consumer、请求/响应、状态机、错误码、幂等、兼容和影响范围。
5. 实现最小授权改动，按所有权运行测试，并记录真实证据。
6. 在提交、PR、合并、发布或运行验收时由 Control 复核范围、契约、安全和 Gate。
7. 任务结束同步状态看板、变更记录、交接说明和 machine context；只写已验证事实。

## 当前 Skill 参考

项目自带 Skill 位于 `.agents/skills/`，其中包括：

- `ai-cs-control`：任务治理与 Gate；
- `ai-cs-agent-engineering`：范围、worktree、测试、提交与推送纪律；
- `ai-cs-runtime-gate`：代码版本与运行实例一致性；
- `ai-cs-interface-owner` / `cross-line-contract-manager`：跨线接口冻结；
- `ai-cs-data-governance` / `knowledge-lifecycle-governor`：资料、知识与审核边界；
- `ai-cs-ai-quality` / `rag-regression-evaluator`：质量证据与 RAG 回归；
- `project-context-maintainer` / `task-gate-reviewer`：上下文同步与验收判定；
- `privacy-and-audit-governor`：敏感资料与审计边界。

本次基础建设任务要求的 `ai-cs-documentation-sync` 未在当前仓库的 Skill 注册中找到，因此文档同步采用 `project-context-maintainer` 的记录规则完成。若后续补充该 Skill，应先更新此列表和使用说明，而不是假定它已经存在。

## 任务卡模板

```md
# TASK: <名称>

## 目标
<可验证的业务或工程结果>

## 范围
- 允许：<目录/服务/文档>
- 禁止：<明确排除项>

## 接口与数据
- Owner：<A/B/C/OPS>
- Provider / Consumer：<...>
- 冻结文档：<docs/control/interfaces/*.v1.md 或“不涉及”>

## 验收
1. <测试或人工证据>
2. <安全/兼容性证据>

## 交付
- 修改文件、测试结果、风险、回滚点、Commit/PR、Gate 结论。
```

## 安全与事实纪律

Agent 不得把页面占位、模拟数据、空状态、计划文档或静态回复描述为真实功能。不得上传/提交密钥、客户资料、数据库、向量库、日志、模型或依赖产物。任何“已启动”“已发布”“已分析”声明都需要对应的运行、Git、接口或测试证据。
