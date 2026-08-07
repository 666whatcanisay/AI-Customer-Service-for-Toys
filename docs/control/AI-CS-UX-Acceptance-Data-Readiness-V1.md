# 《AI-CS UX Acceptance Data Readiness V1》

- Requirement: `R027`
- Date: `2026-08-07`
- Owner: AI-CS Product Acceptance Data Engineer
- Decision: `READY`
- Final Status: `AI_CS_UX_ACCEPTANCE_DATA_READY`

## 1. 验收环境与保护措施

本次只准备 UX 验收数据。正式 Runtime 数据库和正式 RAG 未写入；所有变更位于 Git 忽略的隔离目录 `.runtime/r027-ux-acceptance-data-v1/`。隔离数据库由正式 0013 只读快照复制，并在副本中按既有迁移链升级到 `0016_production_hardening_v1`。

执行前快照时间为 `2026-08-07T00:19:47Z`。数据库备份位于 `.runtime/r027-ux-acceptance-data-v1/source-baseline/standard-platform.sqlite3`，SHA-256 为 `EA7C002D9C968C6D8A291FBBF087599B84602EFA8BA13A0192BE6E9327CD7C57`。RAG 目录备份位于同级 `source-baseline/vector-db/`；最终复核时，正式 RAG 与该备份的同算法目录清单 SHA-256 均为 `F953D75C92E18873119557340ED56D4A9F30B940265F4DD9ED6C162D20961020`。

正式数据库最终 SHA-256 仍为 `EA7C002D9C968C6D8A291FBBF087599B84602EFA8BA13A0192BE6E9327CD7C57`。隔离数据库完整性为 `ok`，最终 SHA-256 为 `1587E6C588B0E5FE66BF71C67B4F1D8104ACABCBB4C48CCA752D5E3582C50633`。

## 2. 账号状态

| 账号 | 状态 | 角色 | 店铺范围 | 登录与首次使用 |
| --- | --- | --- | --- | --- |
| `admin` | ACTIVE | ADMIN | 角色派生的全部店铺 | 真实登录、强制首次改密、旧 Session 撤销、重新登录和退出均通过；验收后恢复为初始化状态 |
| `Wa` | ACTIVE | CUSTOMER_SERVICE | 当前无固定绑定，登录后进入店铺选择流程 | 可读取可选客服店铺；不能访问运营管理接口；验收后恢复为初始化状态 |
| `江` | ACTIVE | OPERATOR | 角色派生的全部运营店铺 | 可访问商品知识运营资源；不能访问用户管理；验收后恢复为初始化状态 |
| `ux_kefu` | ACTIVE | CUSTOMER_SERVICE | 默认绑定测试店铺 `PDD-SM` | Workspace 状态 READY；不能访问运营管理接口；验收后恢复为初始化状态 |

四个账号均通过用户提供的初始化凭据完成最终登录复核，均保留 `must_change_password=true`。验证结束后活动 Session 数为 0。报告未记录密码、密码哈希或 Session Token。

## 3. 角色权限

- ADMIN：用户管理与全部店铺范围通过。
- OPERATOR：商品、SKU、知识运营范围通过；访问用户管理返回 403，权限隔离通过。
- CUSTOMER_SERVICE 主管：店铺选项和首次绑定流程通过；无运营权限。
- 普通客服：只拥有 CUSTOMER_SERVICE 权限，默认店铺为 `PDD-SM`，Workspace 可用；访问运营知识管理返回 403。
- 首次改密前的业务接口统一 fail closed；改密后旧 Session 立即失效；退出后 Session 再次失效。

## 4. 测试知识数据

隔离验收数据使用现有受控测试租户、店铺和商品，不包含真实客户信息：

- 店铺：`PDD-SM`，客服状态 ENABLED，`allow_auto_send=false`。
- 商品：`PDD-SM-P0002`，名称为“6合1巨大型军舰（Q65/Q66灯光款）”。
- SKU：6 个，满足至少 1 个 SKU 的验收要求。
- FAQ：7 条，覆盖商品规格咨询、尺寸、灯光规格、灯串异常、缺件、发货/物流和退换售后。
- 新增受控资料：`KMT-20260807-11356B05A5E5`，状态 `APPROVED_FOR_ANALYSIS`。
- 新增来源：`SRC-UX-R027-P0002-FAQ-V1`，标记 `UX_ACCEPTANCE_ONLY`、`production_usable=false`、`contains_customer_data=false`、`allow_auto_send=false`。

资料通过现有上传、识别、人工审核和增量发布链路处理。商品知识最终状态为 PUBLISHED，活动集合 `test_knowledge_v031` 中共有 70 个向量，其中本商品发布收据为 14 chunks / 14 embeddings；14 个本商品发布片段均带验收 FAQ 来源标识。未执行清空、全量重建、集合重命名或正式 RAG 写入。

## 5. AI 检索结果

测试问题：“这个积木缺件怎么办？”

结果：

- AI 建议：先收集订单号、具体规格、缺件信息和照片，再转人工客服核对；核对前不得承诺补发、退款或赔偿。
- 动作：`TRANSFER_HUMAN`。
- 风险：`HIGH`。
- 必填信息：`order_id`、`missing_part_info`。
- 知识依据：返回 6 条检索来源，且包含审核后的 FAQ 来源 `SRC-UX-R027-P0002-FAQ-V1`。
- 安全提示：同时返回 `SUGGESTION_ONLY` 和 `AUTO_SEND_DISABLED`。

因此“AI 建议、知识依据、风险提示”三项均满足验收要求，且没有自动发送。

## 6. 测试结果

| 检查 | 结果 |
| --- | --- |
| 数据库迁移与完整性 | PASS：隔离副本 0013→0016，`integrity_check=ok` |
| 四账号真实登录 | PASS：角色、ACTIVE、首次改密门禁和最终初始化状态均正确 |
| Session | PASS：创建、改密撤销、退出撤销；最终活动 Session 为 0 |
| RBAC | PASS：admin、运营、客服主管、普通客服权限边界符合要求 |
| 店铺绑定 | PASS：`ux_kefu` 默认绑定 `PDD-SM`；`Wa` 进入店铺选择流程 |
| Workspace | PASS：普通客服 Workspace 为 READY |
| 知识审核与发布 | PASS：1 商品、6 SKU、7 FAQ；PUBLISHED；14/14 发布证据 |
| RAG 检索与 AI 回复 | PASS：建议、来源、HIGH 风险和人工转接均返回 |
| 正式资产保护 | PASS：正式数据库与 RAG 均与执行前备份一致；Git 无数据库、向量、Secret 或日志变更 |

## 7. 安全边界

- 未连接真实 PDD；`CHANNEL_AGENT_ENABLED=false`。
- 未连接生产 Channel Engine。
- 未修改 Gateway Contract、PDD Adapter、Prompt、模型或自动发送逻辑。
- 网络模式为 LOCAL；自动导入和自动知识同步均关闭。
- 未使用真实客户会话、订单、手机号、地址、支付信息或其他客户数据。
- 所有验收知识明确为隔离验收用途，不得复制为生产店铺政策或用于真实客户答复。

## 8. 回滚方式

先停止隔离 Runtime，再将当前隔离数据库和向量目录另行归档；随后可分别从 `source-baseline/standard-platform.sqlite3` 和 `source-baseline/vector-db/` 恢复。若不再需要该验收环境，可在确认报告证据已保留后整体移除 `.runtime/r027-ux-acceptance-data-v1/`。正式 Runtime 不需要回滚，因为本次未修改正式数据库或正式 RAG。

## 9. 剩余风险与下一步

- 数据准备 Gate 已关闭 R026 的 `ENV-001`、`DATA-001`、`ENV-002` 三个数据阻塞，但尚未重新执行四角色 Edge 人工 UX Gate；下一任务应复用本隔离数据重新验收页面流程。
- 发现现有一键启动脚本的无凭据 `/api/chat` smoke 在安全加固后返回 401，导致完整 wrapper 自动清理；本次通过相同受管进程与环境变量分别启动 A/C 完成数据验证。该运行时 smoke 兼容问题不属于数据准备范围，下一轮浏览器验收前应单独修复或使用受控编排，不得放宽 `/api/chat` 鉴权。
- `test_knowledge_v031` 和本报告中的“已发布”只代表隔离验收集合，不代表生产知识已批准。

**Decision: READY**

`Final Status: AI_CS_UX_ACCEPTANCE_DATA_READY`
