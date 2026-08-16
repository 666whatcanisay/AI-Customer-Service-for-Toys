# RC5 最终收口报告

生成时间：2026-08-13（Asia/Shanghai）

## 最终结论

| 项目 | 状态 | 结论 |
|---|---|---|
| `RC5_OFFLINE_STABILITY_READY` | PASS | 离线消息、AI、质量门、人工确认、低风险策略、执行准备、安全门及部署能力已完成 |
| `CURRENT_GREEN_UI_HUMAN_ACCEPTANCE` | PASS | 已保存人工确认后的 Decision、Approval、唯一 ExecutionPrepared 与零真实副作用证据 |
| `RC5_FINAL_READY` | PASS | RC5 离线产品收口完成 |
| `REAL_PDD_PAGE_STRUCTURE_DISCOVERY` | PASS | 已确认官方客服工作台、会话项、消息根、角色标记、商品卡、订单面板和回复框的页面形态 |
| `REAL_PDD_ADAPTER_READY` | NOT_VERIFIED | 尚未冻结无歧义活动会话选择、真实 ID 映射、正式 Observation 与 ACK 链 |
| `REAL_PDD_READ_READY` | NOT_VERIFIED | 尚未完成真实会话/消息/商品/SKU 的端到端读取证据 |
| `REAL_PDD_AI_READY` | NOT_VERIFIED | 尚未以真实消息进入 CustomerContext、AI-CS 和绿色助手 |
| `REAL_PDD_CONFIRM_READY` | NOT_VERIFIED | 尚未以真实会话完成 MANUAL_CONFIRM 证据 |
| `REAL_PDD_SEND_READY` | NOT_VERIFIED | 真实发送仍关闭；不得由当前结果推导 |
| `AI_CS_PRODUCTION_READY` | BLOCKED | 必须等真实 PDD Gate 完成 |

## 本轮 P0 修复

| P0 | 根因 | 修复 | 结果 |
|---|---|---|---|
| 源码、候选包、安装实例无法证明是同一版本 | 旧包 Manifest 没有 Engine/UI 源码身份，最终状态脚本只能比较文件 Hash | Windows Agent Manifest 升至 `2.2`，记录实现提交、Tree、Composition SHA、UI Assets SHA；最终状态脚本增加三段一致性判断 | `source_matches_package=true`、`package_matches_installed=true`、`installed_identity_matches_source=true` |
| RC 版本覆盖安装失败 | 安装器把 `2.0.0rc5` 直接转换为 `System.Version` | 增加受控 RC 版本解析和比较；正式版仍高于相同基础版本 RC | 安装成功，当前安装包与候选包 Hash 完全一致 |
| 最终 BOM 仍指向旧候选包 | 旧 BOM 指向旧 SHA，且明确记录 `matches_current_candidate=false` | 重建候选包、覆盖安装、重新生成 BOM/版本矩阵 | 当前 BOM 指向实现提交 `71fc4eb` / `4d3be2a` 与已安装资产 |

## 当前唯一版本事实

| 对象 | 当前值 |
|---|---|
| Engine Implementation Freeze SHA | `71fc4eb9eb754001e4264736200f64f8340371f3` |
| AI-CS Implementation Freeze SHA | `4d3be2ac3958697d42271439a41557dea784246d` |
| Agent EXE SHA-256 | `a7e443ab2c4b2b179bae38cde11b24a2e2a7e706b29ec6ab54978d32a814817d` |
| Agent PYZ SHA-256 | `4b4832aebef801b91110483c7a1bf2e58a25571db906863918033209a6117f93` |
| Package Manifest SHA-256 | `819c8bcb359196c313a48b5fc4d0ae27596e8fe78bebdba6e3003a0be3f167b7` |
| ZIP SHA-256 | `9e67800add464d72a2bf3624ad6ec3c86b17fc58706b2b32fc59d7bec602f826` |
| Platform Migration Head | `0019_runtime_database_identity_v1` |
| Gateway Wire / Canonical SHA | `1.0` / `e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5` |

Evidence/Docs Commit 与 Implementation Freeze SHA 分开记录。本文档提交不会改变已安装运行资产的实现身份，也不要求重新构建或重启。

## 验证结果

| 验证 | 结果 |
|---|---|
| P0 打包/安装定向回归 | 23/23 PASS |
| PDD Adapter 离线定向回归 | 39 项先前 PASS；最终当前选择集 37/37 PASS |
| 后端黑盒 | 35/35 PASS（复用上一阶段 Full Gate） |
| Engine / Agent | 797 PASS，1 个真实 Edge smoke NOT IN SCOPE（复用） |
| AI-CS Backend | 153 PASS，3 个真实本地 E2E NOT IN SCOPE（复用） |
| Platform / Contracts | 181 PASS / 16 PASS（复用） |
| 绿色助手 / Admin | 216 PASS / 92 PASS + typecheck（复用） |
| Windows 隔离部署 | 13/13 PASS（复用；本轮实际覆盖安装另行成功） |
| Production Architecture | software RC PASS；真实 Selector Gate 按预期 BLOCKED |

本轮只改变打包身份记录、状态采集与安装器版本比较，按 Change Gate 制度没有重复运行全部 1400+ 测试。

## 运行保护与安全

- Agent Identity、Device Binding revision、Store 授权、正式 PDD Profile 身份和配置 Hash 安装前后保持不变。
- 未导出 Cookie、Token 或 PDD Session 内容。
- 当前 `real_send_enabled=false`，正式 PDD 浏览器未由本轮启动。
- 当前浏览器状态 `STOPPED`；Observer 为 `WAITING_IDENTITY`，没有处于扫描状态。
- 本轮未调用 Observer restart，也未生成真实 Observation 或执行页面写操作。
- Controlled Send 仍不进入生产组合；`AUTO_LOW_RISK → 真实发送` 仍未启用。

## 真实 PDD 已确认与未确认

已确认：官方客服工作台路径、可见会话列表、消息容器、CUSTOMER/OPERATOR 结构标记、稳定 message-id 形态、商品卡、订单面板及回复框存在。

仍需真实 PDD 才能确认：

1. 唯一活动会话选择器与稳定 conversation/customer 映射。
2. unread/last activity 归一化及 BOT/SYSTEM 真实证据。
3. 当前 Turn 的 product/SKU ID 映射。
4. 正式 Production Selector Evidence。
5. REAL_PDD Observation → Durable Spool → Host ACK/Cursor。
6. 首个脱敏 Replay 与等价离线回归。
7. 真实消息进入 AI、人工确认以及最后的受控真实发送。

## 冻结能力

Provider 抽象、ACK/Cursor、Agent Identity、Device Binding、Gateway Wire、Execution 安全门、MANUAL_CONFIRM、AUTO_LOW_RISK 离线策略、Synthetic/Real Receipt 隔离均已冻结。无明确 P0/P1 原因不得重构；修改会触发对应消费者、黑盒和 Architecture Gate 重验。

## 非 P0 记录

所有非 P0 项统一记录在 [RC5-Post-Pilot-Issues.md](RC5-Post-Pilot-Issues.md)。当前不拆分三套 PDD Snapshot、不拆 `desktop.py`、不更换 SQLite、不建设远程审计系统。

下一步只进入 `REAL_PDD_ADAPTER_READY → REAL_PDD_READ_READY` 的真实 Pilot，不继续增加治理或外围功能。
