# AI-CS Pilot Baseline Recovery Execution Report V1

> 执行日期：2026-07-29
>
> 需求：R004
>
> Recovery 分支：`control/pilot-baseline-recovery-v1`
>
> 最终 Gate：`CONTROLLED_PILOT_BASELINE_READY`

## 1. 当前问题

已完成的 A 产品投影、C 商品知识运营、C 店铺/商品运营和 Customer
Feedback Loop 分散在多个 Worktree；C 工作区同时混有 B、C、contracts、文档
与临时输出，且可见 contracts 版本为 0.1.0、0.1.1、0.2.0。继续开发会导致
已完成能力无法复现，并使 R006 在错误接口基线上启动。

## 2. 恢复过程

1. 只读确认 develop、Control、A、B、C 的目录、分支、SHA、脏状态、contracts 和端口。
2. 从 clean `develop@671c9a293f1e5e0f462522ad2c7e114c7919c388` 创建独立 Recovery 工作树。
3. 按 A、C、contracts、C Provider、B Consumer 所有权拆成六个能力提交；每次只暂存明确路径。
4. 将共享 contracts 统一为 0.2.0；保留 A `0.3.1-test` 测试知识 schema，不把它并入共享 contracts。
5. 完成 A、C Backend、B、Admin 全量回归、类型检查、构建和 JSON Schema 校验。
6. 使用隔离的 `.runtime` 数据库副本和向量索引恢复四服务；旧 Pilot 数据库未被迁移或写入。
7. 同步 Requirement Registry、运行身份、回滚点和 R006 下一入口。

本次没有新增业务功能，没有执行 R006，没有修改模型、Prompt 或 Business Data Activation 规则。

## 3. 提交列表

| 顺序 | SHA | 内容 | 边界 |
| ---: | --- | --- | --- |
| 1 | `8ebc1bfb6ed0d1208d592b38fbcd904e8d867718` | A Control Center Product Projection | 仅 A Provider、schema model、测试 |
| 2 | `2cf1c3748285e0537667680833aab82dfc6f1596` | C Product Knowledge Operation Center V2 | 商品知识、资料、模板、缺口、C 页面；无 Feedback |
| 3 | `054f4e627d568a7a89a01044ea20e2c528e324c1` | C Store/Product Operation | 店铺/商品创建维护；无激活语义 |
| 4 | `bd837b0b6af03c6b1e29a456c8aca047e98e971c` | Contracts Baseline 0.2.0 | 原 schema、A schema、Feedback schema、版本/兼容/错误码 |
| 5 | `14ecf39dd726efe18be7218ebad6bf2a4f22a52b` | Customer Feedback Loop C Provider | 事件保存、问题中心、知识任务、状态流转 |
| 6 | `acfaa8b574d445cea6039ffa388d54661775b31f` | Customer Feedback Loop B Consumer | `aiInteractionEvent`、采用行为、反馈关联 |
| 7 | 本报告所在提交 | Baseline Documentation | Registry、盘点、测试、运行、回滚与交接 |

任何提交都未使用 `git add .`。

## 4. 最终 SHA 与统一基线

- 可执行能力冻结 SHA：`acfaa8b574d445cea6039ffa388d54661775b31f`。
- 最终基线引用：`refs/tags/ai-cs-pilot-baseline-v1`，指向包含本报告的 Commit 7。
- 统一分支：`control/pilot-baseline-recovery-v1`。
- 统一 contracts：`0.2.0`。
- A 测试知识：继续使用独立 `0.3.1-test`，未改名、未并入 contracts。

Commit 7 只增加控制文档，不改变四服务的可执行代码。最终运行身份以受管
`.runtime/{customer-web,admin-web,rag,platform}.json` 和
`git rev-parse ai-cs-pilot-baseline-v1^{commit}` 为准。

## 5. 测试结果

| Gate | 结果 |
| --- | --- |
| A Backend | `101 passed, 3 skipped`；跳过项均要求显式真实 E2E 环境 |
| C Backend | `95 passed` |
| B Frontend | `28 files / 115 tests passed`；typecheck、production build 通过 |
| C Admin | `25 files / 54 tests passed`；typecheck、production build 通过 |
| Contracts | 7 个 Draft 2020-12 schema 结构校验通过；A 实际产品投影通过对应 schema |
| Migration | Alembic 单一 head：`0008_customer_feedback_loop_v1` |
| Diff/clean | `git diff --check` 通过；正式提交后 tracked 工作区 clean |

现存 warning 为既有 httpx/Starlette 兼容弃用、Vite CJS、VueUse PURE 注释和
前端大 chunk 提示；没有测试失败，也没有把 warning 误写为生产就绪证明。

## 6. 运行方式与身份

| 服务 | 端口 | 工作目录 | 健康检查 |
| --- | ---: | --- | --- |
| B 客服工作台 | 5173 | `<recovery-root>/frontend` | `/` HTTP 200 |
| C Admin | 5174 | `<recovery-root>/admin_web` | `/` HTTP 200 |
| A 能力层 | 8000 | `<recovery-root>/backend` | `/api/health` HTTP 200 |
| C API | 8011 | `<recovery-root>/platform_backend` | `/health` HTTP 200 |

运行恢复使用 `scripts/windows/start_ai_customer_service.ps1` 的受管 PID、监听
PID、仓库根、Git SHA、source fingerprint 和健康核验。四服务均绑定
`127.0.0.1`；未改防火墙、VLAN 或公司网络策略。C 使用旧 Pilot SQLite 的
隔离副本，A 在 Recovery 工作树重建并核对 47/47 知识索引；旧数据库哈希在
复制前后保持不变。

运行时只读冒烟：B、C Admin、A health、C health、A 产品投影、C 商品知识
概览和 C AI 问题列表均返回 HTTP 200。该结果不关闭 R007 的第二终端 LAN Gate。

## 7. 回滚点与未完成事项

回滚点：

- 完全回到恢复前：`671c9a293f1e5e0f462522ad2c7e114c7919c388`。
- 仅保留 A：`8ebc1bfb6ed0d1208d592b38fbcd904e8d867718`。
- 保留 C 商品知识：`2cf1c3748285e0537667680833aab82dfc6f1596`。
- 保留 C 运营：`054f4e627d568a7a89a01044ea20e2c528e324c1`。
- Contracts 0.2.0：`bd837b0b6af03c6b1e29a456c8aca047e98e971c`。
- C Feedback Provider：`14ecf39dd726efe18be7218ebad6bf2a4f22a52b`。
- 完整可执行能力：`acfaa8b574d445cea6039ffa388d54661775b31f`。

未完成事项：

- R003 尚未业务验收；C 新增数据仍没有客服可用激活协议。
- R005 尚未使用真实客服运行证据验证改善闭环。
- R007 第二台客服终端仍受公司网络/VLAN/端口策略 Gate 约束。
- Recovery 分支与本地 tag 尚未被推送或合并；本任务未获授权执行远端发布。

## 8. 下一阶段 R006 入口

下一步只能执行 R006 Interface Freeze，先冻结：

- C 对店铺、商品、SKU 客服可用状态的权威所有权；
- C Provider 与 B Consumer 的读取路径、字段、失败语义和撤回规则；
- contracts 版本策略、部署顺序、兼容与回滚；
- A 使用已激活业务范围时的只读验证边界。

在 Interface Freeze 获批前，R006 保持 `TODO`。不得进入 Business Data
Activation 开发，不得用测试字段、前端判断或 Master Data 重构替代冻结协议。

最终状态：`CONTROLLED_PILOT_BASELINE_READY`
