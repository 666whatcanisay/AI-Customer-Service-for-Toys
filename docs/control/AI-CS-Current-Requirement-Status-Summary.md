# AI-CS Current Requirement Status Summary

> 快照日期：2026-07-30
>
> 唯一需求事实来源：[AI-CS Requirement Registry V1](AI-CS-Requirement-Registry-V1.md)
>
> 当前 Gate：`PRODUCT_IMPORT_MERGE_DESIGN_READY / R009_IMPLEMENTATION_INTERFACE_FREEZE_REQUIRED / TARGET_STANDARD_RUNTIME_UNCHANGED`

本文件是当前状态快照，不是第二份需求台账。任何需求变更必须先更新 Requirement Registry，再同步本摘要。

## 1. 状态统计

| 状态 | 数量 | 需求 |
| --- | ---: | --- |
| `DONE` | 3 | R001、R002、R004 |
| `IN_PROGRESS` | 3 | R003、R008、R009 |
| `TODO` | 2 | R005、R006 |
| `BLOCKED` | 1 | R007 |
| `DEPRECATED` | 0 | 无 |
| 合计 | 9 | R001–R009 |

## 2. 当前需求状态

| ID | 名称 | 状态 | 当前事实 | 下一 Gate |
| --- | --- | --- | --- | --- |
| R001 | C商品知识运营中心V2 | `DONE` | 中文业务展示、知识模板、知识状态和知识缺口已进入正式 Recovery 基线。 | 不得重做结构。 |
| R002 | AI客服反馈沉淀闭环 | `DONE` | 采用状态、反馈保存、C问题中心和知识优化链路已按 B/C/contracts 拆分进入正式基线。 | 真实效果转 R005。 |
| R003 | C新增店铺/商品无法进入B客服 | `IN_PROGRESS` | C能新增、B不能消费；R006 V1.1验证已完成但Implementation仍被两个P0空白阻塞。 | 先关闭IV11-B01/B02，再实施并按目标链路验收。 |
| R004 | AI-CS运行版本统一 | `DONE` | Baseline Tag、独立提交、contracts 0.2.0和全量测试均已建立；R008已把相同受保护应用Tree物化并切换到Target标准Runtime。 | 开发前核验Target目录、SHA、受管记录与contracts；Recovery Tag继续作为回滚保护引用。 |
| R005 | Customer Feedback Loop真实运行验证 | `TODO` | 只有工程和隔离验证，没有真实客服运行后的改善证据。 | 统一基线和业务数据可用后开展受控 Pilot。 |
| R006 | Pilot Business Data Activation V1 | `TODO` | V1.1九个Case得到`6 PASS / 3 CONDITIONAL PASS`；混合来源映射及receipt response/read-back仍未冻结。 | 当前不允许Implementation；只允许关闭IV11-B01/B02。 |
| R007 | 网络环境导致客服无法访问5173 | `BLOCKED` | 当前判断是公司网络隔离、VLAN或端口策略，不是业务代码问题。 | OPS与公司网络管理完成第二终端可达性验收或给出 `NETWORK_SEGMENTED` 结论。 |
| R008 | AI-CS Project Structure Simplification V1 | `IN_PROGRESS` | Runtime Startup Alignment已完成；四服务从clean `dd37927...`运行，活动集合为`test_knowledge_v031=47`，标准启停/status与失败清理已验收。 | 保持Target运行与Recovery锚点；Phase F旧目录处理必须另行授权。 |
| R009 | C运营数据导入升级 V1 | `IN_PROGRESS` | “资料上传与审核”的三步批量Excel、店铺强校验、字段级Merge、待审核与生效收据设计已完成；Import Center保持六模板管理中心。 | 先冻结接口、六模板字段落点和向后兼容数据库迁移；未授权实施。 |

## 3. 当前真正阻塞点

R004已关闭。R006 V1.1业务方向可行，但静态代码映射发现两个实施前P0空白：当前同一旧表同时存在`IMPORTED_TEST_ONLY`和`MANUAL_CREATED`，必须明确迁移为`TEST + ENABLED`与`PILOT + DISABLED`；activation receipt对象虽然已定义，但PUT完整response envelope和持久化receipt复核入口仍不唯一。两项关闭前不能形成可编码contracts。

并行外部阻塞仍为 R007：第二台客服终端的公司网络可达性尚未验收，本轮本机四服务运行成功不等于 LAN Gate 已关闭。

R008 Phase D Retry已关闭PM-D03：失败版和Retry使用相同`26f8cde.../9940eb2...`，唯一批准环境差异为C Python `3.11.9→3.12.13`。本轮重新执行全部矩阵，A `101 passed/3 skipped`、C `95/95`、B `115`、Admin `54`、两端typecheck/build、contracts 0.2.0/7 schema及`0008→0007→0008`隔离迁移全部通过。130个外部临时文件与两端Vitest缓存已清理；7项输入哈希、Target clean、RAG保护目录、Recovery四PID/HTTP和SQLite元数据均不变。

R008 Phase E2已关闭标准端口迁移风险：影子服务先受管停止并释放端口；Recovery最终PID/health、SQLite online backup和RAG manifest已留存；Recovery按Admin→B→A→C停止，Target按C→A→B→Admin启动。当前标准端口全部由Target `26f8cde...`运行，C revision 0008、A ready/47 chunks、B真实合成问题AI建议、Admin实际8000/8011路由均PASS。Recovery目录与数据完整保留但服务已停止。剩余R008工作是单独授权的Phase F和旧Worktree治理，不是再次切换Runtime。

R008 Runtime Handover已将唯一主目录、完整启动环境变量、`green-standard`配置、受管停止/状态命令、四服务职责、B/C本机入口、正式SQLite/RAG路径和Recovery回滚前置条件写成长期交接。该文档不改变Runtime，当前Target仍为同一SHA且clean。未来维护不得省略Target独立数据环境变量、使用旧Worktree或把Recovery当日常开发目录。

R008 Runtime Startup Alignment已关闭Handover后的真实启动回归：活动集合由配置统一为`test_knowledge_v031`，status同时显示实际可见集合；`documents=0`不再阻断启动。最终四服务从clean `dd37927...`运行，A ready/model configured、47 chunks，四条B/Admin代理200且真实Ollama smoke通过。一次中间复验暴露的listener记录清理竞态已通过受控身份回填和清理后双校验关闭。

R009当前真正阻塞点不是页面样式，而是实施接口和正式数据落点尚未冻结：安全规则当前没有商品关系；运营知识缺口不能伪装成A Assessment或无来源的KnowledgeOptimizationTask；AI反馈必须复用去敏、append-only语义；六模板字段到规范列/扩展JSON的映射、状态/错误码/幂等/收据以及Alembic兼容迁移仍需正式评审。设计明确复用`import_batches/import_rows`，保留旧`staged_product_skus`兼容，禁止再建第二套批次/行表。

## 4. 需求依赖与执行顺序

```text
R001 DONE ─┐
           ├─→ R004 Baseline Recovery
R002 DONE ─┘          │
                      ↓
              R006 Interface Validation V1.1 COMPLETE
                      │ CONDITIONAL PASS
                      ↓
              Freeze V1.1 Remediation
                      │ 关闭 IV11-B01 / IV11-B02
                      ↓
              R006 Contracts → C → B → QA
                      │
                      ↓
              R003 业务结果验收
                      │
                      ↓
              R005 真实 Pilot 验证

R007 网络阻塞：由 OPS / 公司网络并行处理

R008 Monorepo Plan READY
  ↓ Source Freeze COMPLETE
R008 Source Clean & Protection Reference Closure COMPLETE
  ↓ Physical Migration Plan READY
R008 Phase 2A Preflight COMPLETE
  ↓ Target Repository Creation COMPLETE
R008 Phase B Source Tag Code Materialization COMPLETE
  ↓ Phase C Dependency Reproduction COMPLETE
  ↓ Phase D Target Validation FAILED（C pytest收集失败）
  ↓ Phase D1 Python Runtime Compatibility CONFIRMED（Python 3.12.13）
  ↓ Phase D2 Target C venv REBUILT（Python 3.12.13）
  ↓ Phase D Retry PASS（完整矩阵）
  ↓ Phase E Runtime Migration Plan READY
  ↓ Phase E1 Green Shadow Runtime PASS
  ↓ Phase E2 Standard Port Cutover COMPLETE
  ↓ Target标准端口持续运行；Recovery停止并保留回滚锚点
  ↓ Runtime Handover READY
  ↓ Runtime Startup Alignment COMPLETE（active collection / start / status / cleanup）
R008 Worktree退役 / Phase F（仍未授权）

R009 Product Import Merge Design READY
  ↓ 仅允许 Interface / Data Mapping / Database Freeze
R009 Implementation（未授权）
```

新功能开发入口仍关闭。R006下一项受控工作仍是Interface Freeze V1.1 Remediation；R008下一项只能是用户另行授权的Phase F；R009下一项只能是导入接口、六模板字段落点和数据库迁移冻结。当前必须按Runtime Handover维护标准端口并保留Recovery。R009设计不授权修改正在运行的Target，也不能把业务数据审核通过解释为R006激活、RAG发布或A分析。

## 5. 防重复结论

- R001 已完成：不要重新设计商品知识结构。
- R002 已完成：不要再次提出“客服行为没有保存”作为新需求。
- R003 是问题记录，R006 是解决任务：不要为同一激活问题创建第三个重复需求。
- R004 已完成：后续开发必须从 Recovery 基线派生，并先复核运行 SHA 与 contracts 0.2.0。
- R007 是网络问题：不要修改 UI 或业务逻辑规避网络隔离。
- R008 Runtime Startup Alignment已完成：不得再固定检查`documents`，也不得把知识warning误写成AI smoke通过；Phase F仍需单独授权。
- R009只改“资料上传与审核”：不得删除或改造Import Center六模板，不得用Excel覆盖/删除数据库，不得让空白清空旧值，不得把资料分析审核状态复用为正式数据审核状态。

最终状态：`PRODUCT_IMPORT_MERGE_DESIGN_READY`
