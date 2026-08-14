# AI-CS PDD Reply Readiness V1 Cross-Repo Handoff

状态：`SOURCE_ONLY / UNCOORDINATED_CANDIDATE`

## 1. 本卡边界

AI-CS 已实现“客户消息已经存在时”的回答就绪度评测、历史修订和隔离风险池。任务卡 7 不实现 Engine 消息入口、不连接 PDD 页面，也不授予发送权。

```text
AI_CS_ENTRY_CONTEXT = DEFERRED_CROSS_REPO
```

这不是任务卡 7 的失败项或完成条件；Engine/CE 当前无需为本卡执行任何修改、重启、迁移、Agent 安装或 PDD Profile 操作。

## 2. 候选 A/C 交接

候选类型位于 `contracts/candidates/pdd-reply-readiness-v1/`：

- `PddReplyReadinessQuestionV1`
- `PddReplyReadinessInputV1`
- `PddReplyReadinessItemResultV1`
- `PddReplyReadinessResultV1`

C 冻结：店铺/商品/SKU、问题集版本和指纹、知识修订及内容哈希、ReplyRule 快照版本和指纹、Router 构建指纹、沙箱向量身份。

Card 8的新生产者使用`knowledge_sources[]`冻结当前商品最新有效审核资料、精确SKU资料和一份可选草稿覆盖；旧`knowledge_snapshot`继续作为兼容输入，两者同时出现必须拒绝。运行投影的`material_id/revision`只指草稿覆盖，完整来源以冻结输入为准。

A 重验：严格 JSON 结构、非生产标志、问题集指纹、当前 ReplyRule 快照、Router 构建、回答哈希、结果哈希、引用与证据包。

正式 `contracts/version.json` 仍为 `0.14.0 / coordinated`。下一共享版本由 A/C 消费侧统一确认，本卡不单方面冻结。

## 3. 未来 Entry Context

以后若要区分主动欢迎、商品卡、订单卡或普通客户文本，应由 Engine 在完成真实消息归一化后生产独立、版本化的入口上下文，并与原始消息/会话 revision 绑定。AI-CS 只消费，不推测页面入口。

未来评审至少需要决定：

- 入口类型枚举及未知值失败关闭；
- 商品卡/订单卡引用和当前会话、客户、店铺的一致性；
- 主动欢迎与客户已经发问的优先级；
- 新客户消息导致旧入口建议失效；
- Entry Context 是否进入 Router 证据和 Engine 授权绑定。

在该契约协调前，AI-CS 按“客户已经发来问题”运行；不得用缺失入口上下文阻塞任务卡 7，也不得把普通问候误写成主动欢迎发送。

## 4. 与自动发送的关系

本卡结果始终：

```text
test_data_mode=true
production_usable=false
allow_auto_send=false
sandbox_vector_identity=in-memory-replay:...
```

`/reply-readiness` 的低风险只是评测结论，不是 `AutoPolicyAuthorizationV2`。Engine Sender、Receipt、真实 PDD Gate、Pilot 和 Production 放量状态均不在本卡内。

## 5. 兼容性

- Gateway Wire：`1.0`，未修改。
- Gateway 原始 Schema SHA-256：`fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`，必须保持。
- 生产 RAG 路径、Prompt、模型和正式向量集合未修改。
- `KnowledgeMaterial` 核心表未修改。
- Engine/CE/PDD 无运行时依赖。
