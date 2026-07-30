# AI-CS Product Knowledge Import V1 Implementation Report

## 1. 交付身份

- 需求：R009 商品知识采集模板导入 V1。
- 基线：`AI-CS@dd379278837a4f816dfb626292a26b0c54cce0cc`。
- 分支：`feature/r009-product-knowledge-import-v1`。
- 实现提交：`871b6290301f8587488bb8b282d4f60034fb37ba`。
- 交付状态：`PRODUCT_KNOWLEDGE_IMPORT_IMPLEMENTED`。

本次只实现“商品知识采集模板 V1.xlsx”。SKU 差异、FAQ、安全规则、AI 反馈和知识缺口五类模板继续展示为“开发中”，选择后明确提示“该模板导入功能暂未开放”。Import Center 的六模板下载、说明和定位没有修改。

## 2. 实现结果

资料上传与审核已形成第一个受控闭环：

```text
选择店铺
  → 选择商品知识采集模板
  → 上传 XLSX
  → 固定规则解析与店铺校验
  → 商品识别与字段级 Merge 预览
  → IDENTIFIED_PENDING_REVIEW
  → 人工通过或驳回
  → 通过后写入正式商品知识 / 驳回后正式数据零变化
```

解析器 `ProductKnowledgeTemplateParser` 只使用 Python 与 `openpyxl`，不调用 LLM。它固定校验“填写说明、数据填写、示例数据、字段说明”四个工作表、工作表标题、固定表头、字段说明、必填项、日期、确认状态、公式、重复商品和最大行数。填写说明被保存在批次模板证据中；字段说明只用于验证代码内冻结映射，不执行动态字段推断。

店铺校验使用当前所选 `store_ref` 对应的完整中文店铺名称。Excel 任一数据行店铺名称不一致时，批次进入 `PREFLIGHT_FAILED`，返回当前店铺和 Excel 店铺信息，不生成可审核变更，更不写正式商品。

## 3. Merge 与正式写入

每个商品生成独立 `ImportChangeSet` 与逐字段 `ImportFieldChange`：

- 商品不存在：生成 `CREATE` 候选；非空字段为 `ADD`。
- 商品存在且 Excel 非空：空旧值为 `ADD`，不同旧值为 `UPDATE`，相同值为 `NO_CHANGE`。
- Excel 空值：为 `KEEP`，合并值保留数据库旧值。
- Excel 未提供的正式数据：不删除、不清空、不重建。

审核前只写导入暂存与审计表。通过时重新计算正式商品快照哈希；快照或版本变化会返回 `STALE_REVIEW_REQUIRED`，不会覆盖并发修改。通过后按字段级 Merge 更新 `test_catalog_products`，附加 `test_source_evidence`，并保持 `publishable=false`。驳回只写追加式审核记录。

新建商品保持 `OFF_SALE`，不创建 SKU。Excel 标记“已确认”时商品知识状态可进入 `APPROVED`，标记“待确认”时保持 `REVIEWING`；两者均不自动发布或激活客服。

## 4. 后端接口

- `POST /api/v1/admin/product-knowledge-imports`
- `GET /api/v1/admin/product-knowledge-imports/{batch_id}/preflight`
- `GET /api/v1/admin/product-knowledge-imports/{batch_id}/merge-preview`
- `POST /api/v1/admin/product-knowledge-imports/{batch_id}/change-sets/{change_set_id}/reviews`

上传与审核都持久化 `Idempotency-Key` 和请求指纹。相同请求重试返回原批次或原收据；同 Key 不同请求返回 `409`；已终结变更不能反向审核。

## 5. 数据库

迁移 `0009_product_knowledge_import_v1`：

- 复用并扩展 `import_batches`、`import_rows`；原商品/SKU 导入字段保持兼容。
- 新增 `import_change_sets`。
- 新增 `import_field_changes`。
- 新增追加式 `import_review_records`。

迁移通过隔离 SQLite 的 `upgrade head → downgrade 0008 → upgrade head` 往返，并通过 `alembic check`。降级只移除 R009 暂存、审核表和扩展列，不撤销已经人工审核写入的正式商品知识。

## 6. Admin 页面

`/knowledge-materials` 保持现有 AI-CS Admin 视觉语言，改为三步批量导入：

1. 选择正常店铺。
2. 选择模板；商品知识模板可用，其他五类显示开发中。
3. 上传 XLSX，展示四表预检、识别统计、商品和逐字段旧值、Excel 值、合并值、变化类型。

运营可逐商品通过或驳回。驳回必须填写原因；页面保存当前批次 ID，刷新后可继续读取该批次。页面明确展示审核前零写入，以及不自动发布 RAG、修改 Prompt、激活客服或执行业务动作。

## 7. 验证结果

- C Backend：`100` 项 pytest 全部通过。
- R009 专项：新增、已有商品 Merge、空值保留、驳回零写入、店铺不一致、未开放模板、上传/审核幂等和反向审核冲突均通过。
- Migration：隔离 SQLite 往返通过；`alembic check` 返回 `No new upgrade operations detected`；最终 revision 为 `0009_product_knowledge_import_v1`。
- C Admin：Vitest `25` 个测试文件、`55` 项测试全部通过。
- C Admin：Vue TypeScript typecheck 通过。
- C Admin：Vite production build 通过。
- `git diff --check` 通过。

测试未连接 Recovery/正式 SQLite，未启动服务，未占用 5173、5174、8000、8011，也未修改当前运行中的 Target Runtime。

## 8. 未实施与后续入口

- 未实现其他五类模板解析和入库。
- 未新增自动脱敏能力；运营仍必须在上传前去除客户个人信息。
- 未新增正式登录、RBAC、保留策略或安全审计平台；`operator` 是审计标签，不是鉴权。
- 未保存上传原文件；批次保存文件名、哈希、模板证据、解析结果和审核证据。
- 尚未把本 Feature 分支迁移到正式 Runtime。部署前必须先备份数据库、执行 `0009`、再做 8011/5174 受控 smoke；本报告不构成 Runtime 切换授权。

禁止在后续工作中把本流程扩展为自动 RAG 发布、Prompt 修改、模型训练、客服自动发送、自动退款或 ERP 写入。

最终状态：`PRODUCT_KNOWLEDGE_IMPORT_IMPLEMENTED`
