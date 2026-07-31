# AI-CS Product Stabilization & Reliability Report V1

执行日期：2026-07-30

最终 Gate：`CONDITIONAL PASS / AI_CS_PRODUCT_STABLE_V1_BLOCKED_BY_R006`

## 1. Runtime 健康状态

- 正式目录：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`
- 正式分支：`stabilization/product-stable-runtime-v1`
- 正式 SHA：`42bafcf6630ccbcd1c2dd1d55cb7d3fe735cb1e2`
- 四服务：5173 B、5174 Admin、8000 A、8011 C API 均 HTTP 200。
- 四服务身份：`runtimeMode=standard`、`networkMode=LAN`，运行记录同仓库同 SHA。
- 数据库：正式 SQLite `0008_customer_feedback_loop_v1`，integrity `ok`；测试前在线备份完成。
- Chroma：active `test_knowledge_v031`，47 chunks；`documents` 为兼容空集合。
- Ollama：`qwen3.5:9b`，模型配置和真实推理通过。
- 三轮 `stop → start → status` 全部通过；A/C 故障模拟和恢复通过。

详细证据见 [Current Runtime Health Report](product-management/Current-Runtime-Health-Report-V1.md)。

## 2. B 客服测试结果

| 场景 | 结果 | 结论 |
| --- | --- | --- |
| B-001 正常商品咨询 | BLOCKED | B 页面和代理健康，但商品目录不可用 |
| B-002 商品不存在 | PARTIAL PASS | B 有可理解错误提示；A 拒答/sources=0 通过 |
| B-003 资料不足 | PARTIAL PASS | A 安全拒答通过；B 选择链路被阻断 |
| B-004 多 SKU | PARTIAL PASS | A 三 SKU 事实与来源隔离通过 |
| B-005 商品切换 | PARTIAL PASS | A P0003/P0005 来源无交叉 |
| B-006 连续 5 轮 | PARTIAL PASS | A API 五轮稳定；B UI 被目录阻断 |

浏览器显示 A、平台可用，但 C 返回的一条不兼容店铺触发 B 清空全部店铺，形成“商品目录暂不可用”。根因和禁止绕过方案见 `BUG-B-001`。这是本次无法宣布产品稳定的唯一 P1 阻塞。

## 3. C 运营测试结果

- 商品管理：隔离环境完成查看、新增、编辑和状态展示，使用合成测试商品且未发布。
- 商品知识中心：字段、状态、R009 审核后内容可见。
- Import Center：六个模板下载入口全部存在，未改变其模板管理定位。
- 商品知识导入：真实 Excel 浏览器上传、预检、Merge、审核通过。
- AI 问题中心：页面正常，空数据时显示真实空状态。

结果：`5 PASS / 0 FAIL`，所有写操作均在隔离 R009 Runtime。

## 4. R009 回归结果

隔离身份：`AI-CS-r009-release-candidate-v1@8b83a20`，Admin 5179、A 19000、C API 19011，隔离 SQLite 从正式 0008 在线副本升级到 0009。

- 真实文件：`商品知识采集模板V1.xlsx`，浏览器 `setInputFiles` 完成真实文件上传。
- Sheet：填写说明、数据填写、示例数据、字段说明全部识别。
- 正常批次：`8aae023a-31e3-4030-9fa8-a0900ab90a61`。
- 识别商品：19；浏览器完成人工审核 19，review outcome 均为 `APPLIED`。
- fresh Merge 预览：ADD 205、KEEP 4；UPDATE、NO_CHANGE 由现有商品合并/重复上传后端回归覆盖。
- 重复上传：幂等 replay/`NO_CHANGE`，没有重复商品。
- 错店铺：整批 `PREFLIGHT_FAILED`。
- 空模板：`PREFLIGHT_FAILED`。
- 缺商品名称：`REQUIRED_FIELD_MISSING`，正式产品表零写入。
- 未开放 SKU 模板：浏览器弹窗“该模板导入功能暂未开放”。
- 100 行：纯代码 Parser 在 1 秒预算内完成 100 条，无 `ROW_LIMIT_EXCEEDED`。

隔离库最终证据：7 batches、57 change sets、627 field changes、19 review records；1 COMPLETED、2 NO_CHANGE、4 PREFLIGHT_FAILED。正式库仍为 0008、无 0009 表、无导入批次。

## 5. AI 质量测试结果

- 知识存在：年龄 P0003 返回 `CONTROLLED_ANSWER`、正确 6～12 岁和安全提示；玩法回答来源属于目标商品。
- 知识不存在：P9999 返回 `REFUSE`、sources=0。
- 资料不足：材质证据不足时拒答，不生成材质。
- 多 SKU：Q65/Q66/Q66-RGB6 各自只返回当前 SKU 来源，颗粒数一致。
- 五轮连续问题：年龄、玩法、小零件、发货、退款动作稳定，无跨商品来源。
- 高风险：退款和吞食小零件均人工转接；保持 `SUGGESTION_ONLY`、`AUTO_SEND_DISABLED`。
- 未修改模型、Prompt、RAG 数据或知识集合。

## 6. Bug 列表

| Bug | 等级 | 状态 |
| --- | --- | --- |
| BUG-A-001 Ollama loopback 请求被代理返回 502 | P1 | FIXED_VERIFIED |
| BUG-A-002 不存在商品命中其他商品知识 | P1 | FIXED_VERIFIED |
| BUG-A-003 年龄误路由/材质无证据生成 | P1 | FIXED_VERIFIED |
| BUG-B-001 单条异常使 B 全目录不可用 | P1 | BLOCKED_BY_R006_IMPLEMENTATION |
| BUG-RUNTIME-001 错误状态入口导致假阴性 | P2 | CLOSED_OPERATOR_ENTRY |
| BUG-A-004 已选 SKU 仍提示确认款式 | P2 | OPEN_DEFERRED |

## 7. Bug 修复记录

修复提交：`18a20f70ec5cd4c4da7baef0179cc30db0dbff5a`；正式部署提交：`42bafcf6630ccbcd1c2dd1d55cb7d3fe735cb1e2`。

修改仅限 `backend/app/service/rag_service.py` 和对应 A 测试：loopback 绕代理、商品范围硬闸门、字段证据充分性检查。未改 Prompt、模型、RAG 数据、UI、contracts、数据库或 R006。

## 8. 新增自动化测试

- `tests/e2e/customer/daily-flow.cjs`：B 每日咨询流；当前会因 `BUG-B-001` 失败，作为 Gate 保留。
- `tests/e2e/admin/operations-smoke.cjs`：商品、知识、Import Center、AI 问题页面。
- `tests/e2e/workflows/r009-product-import.cjs`：真实 Excel 上传、4 Sheet、Merge、审核、重复、错店铺、空模板、未开放模板。
- C 后端补充缺商品名称零正式写入和 100 行 Parser 性能测试。

测试总览：A `105 passed, 3 skipped`；C Backend 全量 PASS，R009 定向 `8 passed`；B Vitest `115 passed`、typecheck/build PASS；Admin Vitest `55 passed`、typecheck/build PASS。构建仅有既有 chunk-size warning。

截图保存在被 Git 忽略的 `tests/e2e/test-results/`，不提交浏览器数据或本地路径产物。

## 9. 剩余风险

1. P1：`BUG-B-001` 阻断真实客服通过 B 选择商品，是稳定发布硬阻塞。
2. P2：明确 SKU 时回答仍有泛化确认措辞；不影响事实和来源隔离。
3. R009 尚未发布到正式 0008 Runtime；本报告只证明隔离 RC 闭环稳定。
4. R009 不负责 RAG 发布，不能把导入成功解释为 B 已能回答新知识。
5. 前端构建有既有大 chunk warning，当前不影响功能，后续性能任务处理。

## 10. 下一阶段建议

1. 单独授权并实施 R006，先关闭 C 最终客服可用投影、单条异常隔离和 activation receipt，再回归 B-001 至 B-006。
2. B 全流程通过后，重新运行 `tests/e2e`，只有全部 suite PASS 才可升级 Gate 为 `AI_CS_PRODUCT_STABLE_V1_READY`。
3. R009 正式发布保持独立任务：正式库备份、0009 升级、Runtime 部署、浏览器只验收 R009，不夹带 RAG 发布。

## 最终状态

`AI_CS_PRODUCT_STABLE_V1_READY`：**未达到**。

实际状态：`AI_CS_PRODUCT_STABLE_V1_BLOCKED_BY_R006`。
