# AI-CS + AI-CE 离线合并上线 V1 状态语义

本文只定义无人值守、无真实 PDD 条件下的 V1 发布事实。机器可读的最终
HEAD、数据库、测试、构建和包指纹在 Full Gate 后写入 Git 忽略的 Release
BOM；BOM 不得把仿真结果伪装成真实 PDD 结果。

## 发布范围

```text
RECORDED_REPLAY
→ Observation
→ Agent / ACK / Cursor
→ Host / Buffer / CustomerContext
→ AI-CS Published ReplyRouter
→ Quality Gate
→ 绿色助手
→ 人工确认或一次性 AUTO Policy
→ 模拟发送
→ 模拟 Receipt
```

- 公共 Observation 使用已有 `provider_kind=RECORDED_REPLAY`；录制来源仅在
  内部 Evidence 中记为 `source_origin=RECORDED_PDD_20260814`。
- 历史 OPERATOR 答案在本轮 Decision 生成前不可进入 Router、RAG 或
  Conversation History，只能作为 Decision 后的 `evaluation_reference`。
- 共享 Receipt 沿用兼容值 `transport_kind=SYNTHETIC_PDD`；内部 Evidence
  使用 `SIMULATED_PDD`，并固定 `simulation_only=true`、
  `external_side_effect=false`。
- `production_real_send_enabled=false` 始终保持；本发布不启动真实 PDD、
  不调用真实 Sender、不产生真实 Receipt。

## 商品和 SKU 语义

- 每条录制样本必须绑定 store、product_ref、可选 sku_ref 和
  scope_evidence。
- 商品级问题只要求 product_ref 唯一；仅当问题或答案依赖 SKU 时才强制
  sku_ref 非空。
- `PRODUCT_SCOPE_ISOLATION_READY`：证据充分且零串用为 `PASS`；证据不足为
  `NOT_VERIFIED`；已有证据证明串商品为 `BLOCKED`。
- `PRODUCT_SCOPE_ISOLATION_READY != PASS` 时，任何模拟 AUTO Gate 必须为
  `BLOCKED_SCOPE_NOT_VERIFIED`。

## V1 Gate

满足双仓最终提交 CLEAN、Full Gate、三个前端构建、正式包和 BOM 绑定后，
允许签署：

```text
PRODUCT_KNOWLEDGE_READY = PASS
RECORDED_REPLAY_REFERENCE_ISOLATION_READY = PASS
PRODUCT_SCOPE_ISOLATION_READY = PASS
SIMULATED_PDD_SEND_READY = PASS
SIMULATED_AUTO_SEND_READY = PASS
OFFLINE_PRODUCTION_E2E_READY = PASS
OFFLINE_UNATTENDED_MERGE_READY = PASS
PROJECT_V1_RELEASED = PASS
```

其中 `PROJECT_V1_RELEASED` 的范围必须写为
`OFFLINE_PRODUCTION_EQUIVALENT_WITHOUT_REAL_PDD`，不能解释为真实拼多多已验收。
以下状态继续保持：

```text
REAL_PDD_ADAPTER_READY = NOT_VERIFIED
REAL_PDD_READ_READY = NOT_VERIFIED
REAL_PDD_AI_READY = NOT_VERIFIED
REAL_PDD_CONFIRM_READY = NOT_VERIFIED
REAL_PDD_SEND_READY = NOT_VERIFIED
REAL_PDD_AUTO_SEND_READY = NOT_VERIFIED
AI_CS_PRODUCTION_READY = NOT_VERIFIED_REAL_PDD
```

## 最终顺序

```text
双仓本地提交并 CLEAN
→ 记录两个 Final HEAD
→ Full Gate（含测试、类型检查和构建）
→ 正式 Windows 包
→ Release BOM
→ 只允许写 Git 忽略的发布报告
→ STOP
```

Full Gate 后若必须修改源码或仓库内正式文档，原 Final HEAD 立即作废；重新
提交后至少重跑受影响核心 Gate，再重新打包和生成 BOM。不要求 Push 或 Tag。
