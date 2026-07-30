# AI-CS Current Requirement Status Summary

> 快照日期：2026-07-30
>
> 唯一需求事实来源：[AI-CS Requirement Registry V1](AI-CS-Requirement-Registry-V1.md)
>
> 当前 Gate：`DEPENDENCIES_REPRODUCED / PHASE_D_NOT_AUTHORIZED`

本文件是当前状态快照，不是第二份需求台账。任何需求变更必须先更新 Requirement Registry，再同步本摘要。

## 1. 状态统计

| 状态 | 数量 | 需求 |
| --- | ---: | --- |
| `DONE` | 3 | R001、R002、R004 |
| `IN_PROGRESS` | 2 | R003、R008 |
| `TODO` | 2 | R005、R006 |
| `BLOCKED` | 1 | R007 |
| `DEPRECATED` | 0 | 无 |
| 合计 | 8 | R001–R008 |

## 2. 当前需求状态

| ID | 名称 | 状态 | 当前事实 | 下一 Gate |
| --- | --- | --- | --- | --- |
| R001 | C商品知识运营中心V2 | `DONE` | 中文业务展示、知识模板、知识状态和知识缺口已进入正式 Recovery 基线。 | 不得重做结构。 |
| R002 | AI客服反馈沉淀闭环 | `DONE` | 采用状态、反馈保存、C问题中心和知识优化链路已按 B/C/contracts 拆分进入正式基线。 | 真实效果转 R005。 |
| R003 | C新增店铺/商品无法进入B客服 | `IN_PROGRESS` | C能新增、B不能消费；R006 V1.1验证已完成但Implementation仍被两个P0空白阻塞。 | 先关闭IV11-B01/B02，再实施并按目标链路验收。 |
| R004 | AI-CS运行版本统一 | `DONE` | 唯一 Recovery 分支、独立提交、contracts 0.2.0、全量测试和四服务同 SHA 运行已完成。 | 继续保持 `ai-cs-pilot-baseline-v1` 为 R006 唯一基线。 |
| R005 | Customer Feedback Loop真实运行验证 | `TODO` | 只有工程和隔离验证，没有真实客服运行后的改善证据。 | 统一基线和业务数据可用后开展受控 Pilot。 |
| R006 | Pilot Business Data Activation V1 | `TODO` | V1.1九个Case得到`6 PASS / 3 CONDITIONAL PASS`；混合来源映射及receipt response/read-back仍未冻结。 | 当前不允许Implementation；只允许关闭IV11-B01/B02。 |
| R007 | 网络环境导致客服无法访问5173 | `BLOCKED` | 当前判断是公司网络隔离、VLAN或端口策略，不是业务代码问题。 | OPS与公司网络管理完成第二终端可达性验收或给出 `NETWORK_SEGMENTED` 结论。 |
| R008 | AI-CS Project Structure Simplification V1 | `IN_PROGRESS` | A/C两个venv、B npm与Admin frozen pnpm安装成功；依赖完整性检查通过，冻结输入哈希不变，Target tracked clean，Recovery未变化。 | 只可另行授权Phase D隔离测试；当前禁止测试、数据库连接和运行切换。 |

## 3. 当前真正阻塞点

R004已关闭。R006 V1.1业务方向可行，但静态代码映射发现两个实施前P0空白：当前同一旧表同时存在`IMPORTED_TEST_ONLY`和`MANUAL_CREATED`，必须明确迁移为`TEST + ENABLED`与`PILOT + DISABLED`；activation receipt对象虽然已定义，但PUT完整response envelope和持久化receipt复核入口仍不唯一。两项关闭前不能形成可编码contracts。

并行外部阻塞仍为 R007：第二台客服终端的公司网络可达性尚未验收，本轮本机四服务运行成功不等于 LAN Gate 已关闭。

R008 Phase C执行成功：Python 3.11.9下A 106项、C Backend 32项分发包安装完成并通过`pip check`；B `npm ci`添加244个包且`npm ls`通过；Admin frozen pnpm复用/安装195个包且list通过。四个依赖目录是Target唯一新增忽略项，7项冻结输入哈希前后一致。Runtime仍为clean Recovery `cbc77ed...`且四服务同PID/health 200；Target没有`.runtime`、数据库、日志或build产物。npm冻结树报告13项漏洞，且Python范围requirements不是完整传递哈希锁，这两项不改变安装Gate但禁止生产安全/严格可重复性声明。

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
  ↓ Phase D隔离测试（等待另行授权）
  ↓ 测试后再进入E–F逐阶段Gate
  ↓ 迁移与运行切换必须分开Gate
R008 运行切换 / Worktree退役（仍未授权）
```

新功能开发入口仍关闭。R006下一项受控工作仍是Interface Freeze V1.1 Remediation；R008下一项只能在明确授权后执行Phase D隔离测试，不得连接Recovery数据库、占用标准端口或切换服务。两个任务互不替代：R008不得实施Business Data Activation，R006也不得借机移动或清理项目目录。

## 5. 防重复结论

- R001 已完成：不要重新设计商品知识结构。
- R002 已完成：不要再次提出“客服行为没有保存”作为新需求。
- R003 是问题记录，R006 是解决任务：不要为同一激活问题创建第三个重复需求。
- R004 已完成：后续开发必须从 Recovery 基线派生，并先复核运行 SHA 与 contracts 0.2.0。
- R007 是网络问题：不要修改 UI 或业务逻辑规避网络隔离。
- R008 已完成依赖复现：不要把`DEPENDENCIES_REPRODUCED`解释为测试通过、依赖安全认证、Target可运行、Pilot已切换或旧目录可退役。

最终状态：`DEPENDENCIES_REPRODUCED`
