# AI-CS master-data.v1 Interface Freeze Plan

> 文档类型：跨线通信契约冻结计划（不含代码、数据库设计或 HTTP/FastAPI 实现）
> 架构依据：[AI-CS Business Data Architecture ADR V1.1](../architecture/AI-CS-Business-Data-Architecture-ADR-V1.1.md)
> 架构状态：`ARCHITECTURE_DECISION_FROZEN`
> 本计划 Gate：`INTERFACE_FREEZE_REQUIRED`
> Interface Owner：Control / AI-CS Interface Owner
> Business Truth Owner / Provider：C — AI 运营中心
> Consumer：B — 客服工作台；A — AI 能力层
> 共享 contracts 当前版本：`0.1.0`，本文件本身不修改该版本，也不授权实现。

## 1. Interface Freeze Summary

Productization V2、主数据 ADR、Knowledge Lifecycle 和 AI Context Layer 已冻结业务架构方向：C 管理业务真相，B 仅使用已授权业务投影，A 仅消费 C 已发布的最小 Serving 数据。本阶段必须把这一方向转成可由 B/C/A 独立实现、联调和回放的通信契约。

没有接口冻结时，以下链路会失去可控性：

```text
C 变更字段、范围或版本
          ↓
B 继续按旧字段选择或展示
          ↓
A 得到不可验证的 Tenant / Store / Product / SKU 上下文
          ↓
检索范围、回答追溯和质量证据发生错误
```

本计划的最终目标是稳定 B/C/A 协作，而不是创建新的业务能力：

- C 是唯一 Business Data Provider 和业务事实 Owner；
- B 只消费可见目录、提交受控选择引用和显式反馈；
- A 只消费 C 解析后的 Context 与已 Release 的知识，生成建议回复和非执行性质量证据；
- 所有跨线数据均可关联到同一 Tenant、Store、Listing、主数据 revision、Knowledge Release 和 `answer_trace_id`；
- 浏览器输入不成为权限证明，A 的模型输出不成为业务事实或自动动作。

本文件仅冻结通信语义、字段、可见性、版本、兼容和 Gate。它不创建路由、数据表、认证产品、前端页面、迁移、PR 或部署。

## 2. Interface Ownership Model

| 角色 | 冻结职责 | 可以提供 / 消费 | 明确不可以做 |
|---|---|---|---|
| C：Business Data Provider | Tenant、Store、Canonical Product/SKU、Store Listing、External Mapping、Knowledge Release、Context 与追溯证据的唯一业务真相 Owner | 向 B 提供授权目录投影；向 A 提供受控 Context 和已发布 Serving 快照；接收质量证据 | 让 B/A 直接写业务真相；把导入、审核或模型建议自动变成 Release；自动执行业务动作 |
| B：Human Operation Consumer | 客服使用 AI 的交互 Consumer | 消费 C 的最小目录投影；向 A 发送问题与 `context_ref`；向 C 提交显式反馈/案例引用 | 维护 Product/SKU/Listing 关系；用浏览器字段授予 Tenant/Store 权限；访问原始资料、审核记录或 C/A 数据库 |
| A：AI Capability Consumer | RAG、模型、风险判断、回答追溯与质量分析 Consumer | 消费 C 解析后的 Context 与 Knowledge Release；向 B 返回建议回复；向 C 返回非执行性质量证据 | 创建、合并或修改主数据；发布/撤回知识；读取未发布资料；把建议自动写入 Prompt、知识、模型、客户或订单 |
| Control / Interface Owner | 维护语义、版本、兼容性和跨线 Gate | 审查 C Provider、B/A Consumer 的契约一致性 | 替任何线路实现业务代码，或把设计冻结误称为上线能力 |

### 2.1 业务对象独立性

`master-data.v1` 管理范围和版本引用，不替代既有 `CustomerSuggestion`、`CustomerExperienceCase`、`AIResponseFeedback` 或 `CustomerEfficiencyEvent`。这些实体只能引用下列受控标识或不可变快照，不能共用状态机、ID 语义或生命周期：

- `tenant_id`、`store_id`；
- `product_id`、`sku_id`；
- `store_product_listing_id`、`store_sku_listing_id`；
- `catalog_revision`、`knowledge_release_id`、`answer_trace_id`。

历史字符串 `store_code/product_id/sku_id` 保留为 legacy snapshot；未经 C 人工精确确认，不得按名称、向量相似度或模型推断回填为新主数据引用。

## 3. Interface Boundary Diagram

```text
                         C — AI 运营中心
              Business Truth / Business Data Provider

      Store / Product / SKU Listing     Knowledge Release
      Catalog Snapshot / Context Ref    Serving Snapshot
                    |                         |
                    |                         |
                    +-------------> B          +-------------> A
                                  客服工作台                    AI 能力层

      B -- 问题 + context_ref --------------------------------> A
      A -- 建议回复 + answer_trace_id ------------------------> B

      B -- 显式反馈 / 案例 + answer_trace_id -----------------> C
      A -- Quality Evidence（仅证据，不执行）-----------------> C
```

边界解释：

1. B 从 C 消费的是已授权、可展示的目录投影，不是主数据维护权限，也不是原始映射或知识材料。
2. B 向 A 传递的是问题和 C 发放的短期 `context_ref`；Tenant、Store、Product、SKU 不是由 B 直接断言为可信事实。
3. A 以服务身份向 C 解析 `context_ref` 并消费匹配范围、有效期内的 Knowledge Release；A 不直接访问 C 数据库。
4. A 对 B 的回复必须带 `answer_trace_id`，使后续 C 的反馈、案例和质量证据可回放到当时的范围与版本。
5. A 向 C 写入的是质量证据和建议，不是主数据、知识发布、Prompt 修改或任何客户/订单动作。

## 4. Contract Families and Direction

本阶段冻结五个逻辑 contract family。名称是契约标识，不代表已经创建路径或服务。

| 契约 | Provider | Consumer | 目的 | 浏览器可直接调用 |
|---|---|---|---|---|
| `catalog-master.v1` | C | B | 已授权 Store、Product、SKU Listing 的只读选择投影 | 仅经 B 的已认证 C Consumer 边界 |
| `catalog-serving-context.v1` | C | A | 将 B 的受控选择引用解析为 A 可消费的范围快照 | 否；仅 A 服务身份 |
| `knowledge-release.v1` | C | A | 已发布、可撤回、带有效期的最小 Serving 知识快照 | 否；仅 A 服务身份 |
| `ai-answer-trace.v1` | A 生成；C 持久化/审计 | B、C、A、QA | 将回答、上下文、知识和模型版本关联 | B 只消费最小可展示投影 |
| `quality-evidence.v1` | A | C | 保存非执行性的模型质量分析证据 | 否；仅 A 服务身份 |

`catalog-promotion.v1` 属于 C Admin/QA 的内部治理契约，不是 B/A 通信契约；其结果只通过 `catalog-master.v1` 和 `knowledge-release.v1` 对外可见。

## 5. Common Contract Rules

### 5.1 Version envelope

每个跨线载荷必须带有以下可观察元数据；字段名、类型和语义在 schema 冻结时不得复用或静默改义。

| 字段 | 类型 | Provider | 规则 |
|---|---|---|---|
| `contract_version` | string | Provider | 固定为相应 family 的 `*.v1`；Consumer 不兼容时失败闭合 |
| `schema_revision` | positive integer | Provider | 同一 major 内单调增加；用于解析和回放 |
| `request_id` | opaque string | 接收方 / Provider | 每次跨服务调用可追溯；不得承载用户或业务内容 |
| `generated_at` | RFC 3339 UTC datetime | Provider | 服务端生成，不接受 Consumer 覆盖 |
| `scope` | object | C | 见第 6 节；B/A 不得把其作为自行授权的来源 |
| `data_classification` | enum | C | `TEST`、`PILOT_DEIDENTIFIED`、`PRODUCTION_APPROVED`；未知值失败闭合 |

共同规则：对象未知字段只能在 schema 声明为可扩展时忽略；未知必填字段、枚举、状态、错误码、版本冲突或范围不匹配必须失败，不得本地猜测、自动降级或以测试目录替代。

### 5.2 Error and retry envelope

所有 Provider 使用统一语义：

```json
{
  "error": {
    "code": "MASTER_DATA_SCOPE_MISMATCH",
    "message": "The requested context is outside the authorized business scope.",
    "retryable": false
  },
  "request_id": "opaque-request-id"
}
```

| 错误码 | Consumer 行为 |
|---|---|
| `MASTER_DATA_SCOPE_MISMATCH` / `TRACE_SCOPE_FORBIDDEN` | 停止展示或执行；重新选择已授权范围；不重试 |
| `MASTER_DATA_NOT_FOUND` / `CONTEXT_INVALID` | 显示受控失败；不按名称猜测替代对象 |
| `CATALOG_REVISION_RETIRED` / `KNOWLEDGE_RELEASE_WITHDRAWN` / `KNOWLEDGE_RELEASE_EXPIRED` | 刷新 C 投影并重新取得 Context；不得继续使用缓存事实 |
| `VERSION_CONFLICT` | Consumer 停止当前流程，读取兼容版本或升级 adapter |
| `IDEMPOTENCY_CONFLICT` | 不覆盖原请求；由发起方建立新的明确业务操作后再提交 |
| 暂时不可用 | 仅可重试明确标记为 `retryable=true` 的读请求；写入沿用同一幂等键 |

## 6. Scope, Identity and Permission Boundary

### 6.1 Authoritative scope

所有业务事实均处于如下范围中：

```text
tenant_id
  → store_id / store_code
  → store_product_listing_id → product_id
  → store_sku_listing_id     → sku_id
  → catalog_revision / knowledge_release_id
```

`tenant_id`、可访问 Store、角色和数据分类必须从服务端认证上下文解析。浏览器或 A 请求体中的 `tenant_id`、`store_code`、`created_by`、产品名称、外部 ID 都只能是业务输入或显示线索，不能授予访问权。

### 6.2 Permission matrix

| 调用主体 | 必需逻辑权限 | 可见数据 | 不可见 / 不可做 |
|---|---|---|---|
| B 客服身份 | `catalog.read`、`answer.request`、`feedback.create` | 被授权 Store 的展示目录、可展示回答和自身显式提交回执 | 其他 Tenant/Store、External Mapping、审核备注、原始资料、未发布知识 |
| A 服务身份 | `context.resolve`、`knowledge.release.read`、`quality_evidence.write` | 已授权范围的最小 Context、已 Release Serving 内容和版本元数据 | B 身份、未审核/未发布资料、C 数据库、主数据/知识写入或发布权限 |
| C 运营审核身份 | `catalog.review`、`catalog.promote`、`knowledge.release`、`trace.read` | C 内部审核投影与审计证据 | 以审核身份替 A 生成模型结论，或绕过 Tenant 范围 |
| QA / OPS | 明确的隔离验证 scope | 经过批准的测试/去标识化投影 | 生产敏感内容、业务事实改写、协议语义改动 |

认证、RBAC、服务身份、访问审计和保留策略尚未实现或验证；本计划定义其接口前提，不宣称现有端口 `5173`、`5174`、`8000` 已具备上述控制。

## 7. Frozen Data Projections

### 7.1 C → B: `catalog-master.v1`

B 只依赖可展示、已授权且状态为 `ACTIVE` 的目录投影：

| 字段 | 类型 / 可空性 | 可见性与语义 |
|---|---|---|
| `catalog_revision` | string，非空 | C 当前目录版本；B 缓存与选择必须绑定该值 |
| `store` | object，非空 | `store_id`、`store_code`、`display_name`、`channel`、`status`；只包含授权 Store |
| `products[]` | array | `store_product_listing_id`、`product_id`、`product_name`、`listing_display_name`、`status`、`catalog_revision` |
| `skus[]` | array | `store_sku_listing_id`、`sku_id`、父 `store_product_listing_id`、`sku_display_name`、`status`、`catalog_revision` |
| `selection_context_ref` | opaque string，可空 | C 为已授权选择发放的短期引用；B 不解析、不伪造、不跨 Store 复用 |
| `expires_at` | RFC 3339 UTC datetime，可空 | 若有 `selection_context_ref` 则必填；过期后 B 必须重新向 C 获取 |

禁止出现在 B 投影中：外部平台/ERP 映射、审核备注、导入暂存、原始知识材料、知识正文、未发布状态、其他店铺/租户记录、内部路径、密钥、客户数据。

### 7.2 B → A: `ai-context-request.v1`

这是 B 对 A 的受控调用载荷；它不把 B 升格为业务事实 Provider。

| 字段 | 类型 / 可空性 | B 提供的语义 |
|---|---|---|
| `question` | string，非空 | 客服当前问题；不得混入身份、订单、地址、密钥或原始资料 |
| `context_ref` | opaque string，非空 | 来自 C 的 `selection_context_ref`；A 必须向 C 解析 |
| `catalog_revision` | string，非空 | B 取得 Context 时的版本；不一致时 A 失败闭合 |
| `client_request_id` | opaque string，非空 | B 的调用追踪；不作为幂等、身份或权限依据 |

B 不得把 `tenant_id`、`store_id`、`product_id`、`sku_id`、Knowledge ID 或权限角色作为 A 可直接信任的范围输入。A 不得在 `context_ref` 无效时用旧缓存、商品名称或测试默认范围继续回答。

### 7.3 C → A: `catalog-serving-context.v1`

`context_ref` 只能由 A 的服务身份向 C 解析。返回的是 A 进行范围过滤所需的最小不可变快照：

| 字段 | 类型 / 可空性 | 规则 |
|---|---|---|
| `context_ref` | opaque string，非空 | 必须与 A 请求一致 |
| `context_snapshot_id` | opaque string，非空 | C 生成；用于 `answer_trace_id` 关联 |
| `scope` | object，非空 | `tenant_id`、Store/Listing/Canonical Product/SKU ID；C 已验证父子和同 Tenant 关系 |
| `catalog_revision` | string，非空 | 已解析目录版本 |
| `valid_until` | RFC 3339 UTC datetime，非空 | A 过期后不得继续用于新回答 |
| `data_classification` | enum，非空 | 与当前调用和知识 Serving 必须一致 |
| `scope_hash` | string，非空 | C 对规范化 Scope 快照计算；A 回写 trace 时原样携带 |

### 7.4 C → A: `knowledge-release.v1`

A 只能消费状态为 `RELEASED`、范围匹配、未过期且未撤回的 Serving Snapshot。资料上传、材料审核、质量分析或知识草稿均不是 A 可消费的数据。

| 字段 | 类型 / 可空性 | 规则 |
|---|---|---|
| `knowledge_release_id` | opaque string，非空 | C 生成的发布标识 |
| `release_revision`、`content_hash` | string，非空 | 固定该次 Serving 内容，支持回放 |
| `scope_bindings` | object，非空 | 必须与 Context Snapshot 的 Tenant/Store/Product/SKU/Listing 范围兼容 |
| `effective_at`、`valid_until` | RFC 3339 UTC datetime | A 在有效期之外不得 Serving |
| `release_status` | enum，非空 | 仅 `RELEASED` 可被 A 使用；`WITHDRAWN`、`EXPIRED` 必须停止使用 |
| `serving_content` | approved, bounded content | 仅已批准知识的 Serving 载荷；不是原始材料、文件、向量、日志或完整内部来源 |
| `source_refs[]` | array | 仅可展示/追溯的受控来源标识与 revision/hash；不含原文、路径或密钥 |

### 7.5 A → B and A → C: answer trace and quality evidence

A 给 B 的回答最小投影：`answer`、`action`、`risk_level`、`warnings`、`required_fields`、可展示 `sources`、`answer_trace_id`。B 不得将内部检索片段、Prompt、模型密钥或未展示来源写入页面或本地存储。

`answer_trace_id` 在 C 的追溯记录中至少绑定：

- `context_snapshot_id`、`scope_hash`、`catalog_revision`；
- `knowledge_release_id`、`release_revision`、`content_hash`；
- `model_version`、`prompt_policy_version`、`retrieval_policy_version`、`run_id`；
- 时间、数据分类及最小可审计状态。

A → C 的 `quality-evidence.v1` 只能提交 `answer_trace_id`、版本引用、质量结论、受限建议、`analysis_run_id` 和幂等信息。它不能包含主数据修改、知识发布、Prompt 指令、训练指令、客户文本、订单信息或自动执行标记。

## 8. Lifecycle, Idempotency and Visibility

| 对象 | 可见状态 / 转换 | B 可见性 | A 可见性 |
|---|---|---|---|
| Catalog / Listing | 仅 `ACTIVE` 可进入目录；`RETIRED` 不可新选 | 仅 `ACTIVE` 的授权投影 | 间接通过已解析 Context 使用 |
| Knowledge Release | `RELEASED` 可 Serving；`WITHDRAWN`、`EXPIRED` 停止 Serving | 不直接查看未发布/已撤回内容 | 仅 `RELEASED` 且范围、有效期匹配 |
| Context Snapshot | C 发放 → 有效 → 过期/撤销 | 仅 `context_ref` | 仅成功解析的最小快照 |
| Answer Trace | A 生成 → C 持久化/审计 | 仅自身回答的最小引用 | 自身运行证据 |
| Quality Evidence | A 提交 → C 保存为人工审阅证据 | 不直接读取完整分析 | 只读自身受控回执 |

幂等要求：

- 目录、Context 解析和 Knowledge Release 读取无副作用，可安全重试；
- C 发放或更新会产生可观察事实的 Context/Release/Promotion 操作，必须在后续正式冻结中定义 `Idempotency-Key`、相同键重放、同键异负载冲突和并发语义；
- A → C 质量证据以 `analysis_run_id + answer_trace_id` 为幂等范围；相同完整载荷重放原回执，不同载荷返回冲突；
- B → C 反馈、案例及效率事件继续使用各自既有的幂等契约，不能借用 `answer_trace_id` 替代业务幂等键。

## 9. Version, Compatibility and Migration Rules

1. `master-data.v1` 是本计划的逻辑 family 标签，不等于已发布的共享 `contracts` 版本；当前共享版本保持 `0.1.0`。
2. v1 内只能增加可选且非敏感字段；不得改变既有字段类型、可空性、枚举语义、Scope 语义、错误码含义或可见性。
3. 删除字段、把可选改为必填、扩展状态/枚举、改变数据分类、降低权限或保留阈值，必须创建 v2 并完成 B/C/A 兼容评审。
4. 迁移期实行“按 Tenant/Store 确定性双读，不混读”：已迁移范围读新目录；测试 Pilot 读明确标记的 test/legacy 目录；未映射或冲突返回 `REVIEW_REQUIRED`。
5. 旧 `store_code/product_id/sku_id` 字符串是历史快照，不能被名称相似或 AI 推断替换；历史 trace/反馈不得重写。
6. 回滚不删除业务事实：通过 `RETIRED`、`WITHDRAWN` 或切回上一已批准 revision 恢复服务，并保留审计与回放证据。

## 10. Required Freeze Artefacts and Acceptance

在任何 B/C/A 实现、PR 合并或真实联调之前，以下资料必须由 C Provider、B Consumer、A Consumer、QA 和 Interface Owner 共同确认：

1. 每个 family 的正式 JSON Schema、版本号、字段字典、枚举、最大长度、敏感字段规则与样例；
2. 传输绑定：方法/路径、认证 audience、超时、分页、缓存、幂等和完整错误码；
3. C 的认证/RBAC、A 服务身份、Tenant/Store 范围解析、访问审计及保留/清理决定；
4. B/A 的未知字段、未知状态、撤回、过期、范围冲突和版本冲突失败行为；
5. changelog、兼容矩阵、迁移范围表、双读路由、回滚条件和废弃日期；
6. 真实 QA：跨 Tenant/Store 拒绝、Listing 父子关系拒绝、过期/撤回 Knowledge 拒绝、同幂等键重放、Answer Trace 回放、B → C → A → C 最小闭环。

### Gate decision

`INTERFACE_FREEZE_REQUIRED`

理由：ADR V1.1 已冻结 Provider/Consumer 架构和业务边界，但尚未完成每个 family 的正式 schema、传输绑定、认证/RBAC、服务身份、保留审计、兼容矩阵和验收证据。本计划不构成实施授权；在上述资料完成并签字前，B、C、A 均不得自行猜测字段、创建兼容别名或进入跨线实现。
