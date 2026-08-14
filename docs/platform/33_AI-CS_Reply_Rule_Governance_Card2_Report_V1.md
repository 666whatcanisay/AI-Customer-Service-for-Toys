# AI-CS Reply Rule Governance Card 2 Report V1

日期：2026-08-14

Gate：`PASS / AI_CS_REPLY_RULE_GOVERNANCE_CARD2_READY / SOURCE_ONLY`

协调状态：`CROSS_REPO_UNCOORDINATED`

## 1. 交付结果

C线已经具备固定回复规则的最小治理闭环：创建草稿、只允许草稿编辑、提交审核、批准或驳回、创建下一不可变版本、查询和最小审计。发布、撤回、C→A快照以及Router消费不属于卡2，将在后续任务卡实现。

规则批准前必须同时满足：

- 规则业务范围与C目录中的租户、平台、店铺、商品和SKU一致；
- 引用资料的当前版本已经通过既有人工审核；
- 资料范围没有跨店、跨商品或跨SKU；
- 普通事实已人工确认；高风险规则另有高风险来源确认；
- 规则未过期，固定变量仅使用批准的五个变量；
- 自动候选只允许低风险直接回答或白名单中风险受控回答/澄清。

## 2. Reuse First审计

| 能力 | 复用结论 |
| --- | --- |
| 人工审核事实 | 复用`KnowledgeMaterial`及`APPROVED_FOR_ANALYSIS/ANALYZING/ANALYZED`状态，不另建来源审核系统 |
| 版本与不可变性 | 复用C的不可变revision原则；仅因固定别名、动作、风险和模板变量无法由现有实体表达，最小新增`reply_rules`版本实体 |
| 生命周期审计 | 复用同一SQLAlchemy/Alembic数据库和服务端身份，最小新增不含问题/回复正文的`reply_rule_events` |
| RBAC | 复用`knowledge.manage`，没有第二套角色、权限或认证 |
| Store/Product/SKU权威 | 复用C现有目录模型并在写入和批准时校验范围 |
| 发布与收据 | 卡2不实现；卡3复用现有发布租约、幂等和receipt模式，不提前复制框架 |
| Admin界面 | 卡2不新建页面，避免在治理模型稳定前扩大UI开发量 |
| 数据库 | 复用唯一Platform数据库；没有A侧SQLite、第二数据库或Runtime写入 |

## 3. 数据和接口

源码迁移Head为`0020_reply_rule_governance_v1`，纯新增：

- `reply_rules`：按`rule_id + rule_version`保存治理版本；审核后不可原地编辑。
- `reply_rule_events`：只保存动作、状态、操作者、原因、内容指纹和时间，不复制标准问题、别名或固定回复正文。

C本地Admin接口：

- `POST/GET /api/v1/admin/reply-rules`
- `GET/PUT /api/v1/admin/reply-rules/{rule_id}/versions/{version}`
- `POST .../submit-review`
- `POST .../review`
- `POST /api/v1/admin/reply-rules/{rule_id}/versions`
- `GET /api/v1/admin/reply-rules/{rule_id}/events`

所有接口要求既有Bearer身份和`knowledge.manage`权限。操作者由服务端Principal产生，不接受客户端伪造。

## 4. Change Gate

```powershell
cd platform_backend
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

- Alembic单一Head：`0020_reply_rule_governance_v1`。
- 卡2定向：`7 passed`。
- C线全量：`188 passed`。
- 迁移在临时SQLite中完成`0019 → 0020 → 0019 → head`往返。

## 5. 兼容与运行边界

- Gateway Wire仍为`1.0`，冻结Schema和SHA未修改。
- `contracts/version.json`仍为`0.14.0 / coordinated`；卡2没有单方面冻结共享版本。
- 受控RC5 Runtime仍为`0019_runtime_database_identity_v1`；本轮没有迁移、备份、启动或停止正式服务。
- 没有修改Engine、A Router、RAG、Prompt、模型、知识向量、PDD Adapter或发送能力。
- `AI_CS_AUTOREPLY_READY`尚未签署。

## 6. 下一任务

卡3复用现有发布租约、幂等、内部服务鉴权和receipt做C→A完整有效规则快照；发布失败时A继续使用上一有效快照。卡3不得新增第二套权限体系或独立数据库。
