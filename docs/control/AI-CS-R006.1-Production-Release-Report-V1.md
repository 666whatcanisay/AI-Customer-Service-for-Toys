# AI-CS R006.1 Production Release Report V1

> 发布日期：2026-07-31  
> 正式目录：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`  
> 发布分支：`release/r006-1-knowledge-activation-v1`  
> Release 代码 SHA：`55ca6eb4ee451dd667d0fbacc8c4d07db3d7fd39`  
> 来源实现：`feature/r006-1-knowledge-activation-v1@f181c00c566bd10dcfaff6e5fa516931f0db3ab3`  
> 最终状态：`R006_1_PRODUCTION_RELEASE_COMPLETE`

## 1. 发布结论

R006.1 已部署到正式 AI-CS Runtime。商品知识从人工审核、商品级 AI 知识增量发布、客服人工启用，到 B 选择商品并由 A 使用同商品知识回答的链路已在正式端口完成浏览器 Smoke。

本次未改变 R009 Excel 导入规则、Import Center 定位、B 客服业务步骤、Prompt、模型和自动业务执行边界。客服状态变化不会触发向量化；只有正式商品知识内容变化才进入 `NEED_RESYNC`，运营重新发布后恢复 `PUBLISHED`。

## 2. Release 内容

Release 包含：

- A 接受 C/B 提供的新业务上下文，不再限制历史 TEST 店铺字面量，也不判断商品权限。
- contracts `0.4.0` 的 AI 知识状态、发布请求/回执和可见性契约；保留 `0.3.0` Customer Available Catalog 兼容能力。
- C `0011_product_knowledge_publishing_v1`、五态 AI 知识生命周期、商品级 fingerprint、publication receipt、增量发布与批量客服启用。
- Admin 商品知识中心展示审核、客服、AI 三个独立状态，提供发布、重新同步和批量启用入口。
- B 基于 C 权威只读投影展示真实 AI 知识状态、引用数量和发布回执，不自行判断商品可信度。
- Windows 运维测试兼容与标准 LAN Runtime 本机 Admin CORS 修复。

## 3. BUG-B-002 修复结果

状态：`FIXED_VERIFIED_PRODUCTION`

B 原“参考准备度”不再读取旧知识资料审核投影，改为读取 C 的商品级 AI 知识状态接口。正式浏览器验证显示：

- `AI知识状态：已发布`
- 引用数量：`3`
- 发布回执：`RAG-0b5a7648cd1fdb836678c9790c439e32`

C 负责验证 `PUBLISHED` 必须同时具有有效发布回执、`chunk_count > 0` 和完整 embedding 证据；B 只展示 C 的最终结果。

## 4. BUG-RUNTIME-003 修复结果

状态：`FIXED_VERIFIED_PRODUCTION`

旧 OPS T04 测试夹具已兼容 PowerShell 原生命令错误流，过期 PID、缺失 Runtime 目录、仅 C 运行等降级场景不再被父 Shell 提前中断。未削弱正式状态脚本的 PID 身份校验、错误输出和安全停止规则。

回归结果：

- `Test-OpsT04Fix1.ps1`：PASS
- `Test-OpsLanMode.ps1`：PASS
- `Test-OpsRuntimeFix2.ps1`：PASS

发布 Smoke 另发现并关闭 `BUG-RUNTIME-004`：标准 LAN Runtime 现在只额外允许本机 `127.0.0.1:5174` 和 `localhost:5174` 访问 C/A，不向 LAN 暴露 Admin 5174，也不使用 CORS 通配符。

## 5. 数据库备份与 0011 迁移

正式数据库迁移前完成在线备份和离线回滚快照。备份目录：

`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS\.runtime\phase-e\green-standard\pilot-backups\r006-1-production-release-20260731-134619`

| 资产 | SHA256 / 校验 | 结果 |
| --- | --- | --- |
| `standard-platform.0010.online.sqlite3` | `47efe1bb0d627474ef42b83caf51bd40987097e6cadc292121d548772a1b7226` | revision 0010；`integrity_check=ok` |
| `standard-platform.0010.offline.sqlite3` | `47efe1bb0d627474ef42b83caf51bd40987097e6cadc292121d548772a1b7226` | revision 0010；`integrity_check=ok` |
| `rag-vector-db.0010.offline` | manifest SHA256 `763ebfd5be7e4545a73e3bed2dd3a3cba2182adf5975b412a44af5da1f13418a` | 5 个文件、1,038,500 bytes，与源快照一致 |

迁移结果：

```text
0010_customer_available_catalog_v1
  ↓
0011_product_knowledge_publishing_v1
```

- 正式 Alembic revision：`0011_product_knowledge_publishing_v1`
- SQLite `integrity_check`：`ok`
- R009 原有商品、导入批次和审核数据在迁移后保持可读。
- R006 activation receipt 保持正常。
- 未在正式数据库执行 destructive downgrade。

## 6. 测试结果

| 范围 | 结果 |
| --- | --- |
| A Backend | `108 passed, 3 skipped` |
| C Platform Backend | `117 passed` |
| B Frontend | `28 files / 117 passed`；typecheck、build PASS |
| C Admin | `27 files / 63 passed`；typecheck、build PASS |
| Contracts | `5 passed`；version `0.4.0` |
| OPS | T04、LAN Mode、Runtime Fix 2 全部 PASS |

仅保留非阻塞告警：Vite CJS deprecation、前端大 chunk 告警和既有 pytest deprecation。没有修改依赖版本来消除这些告警。

## 7. 正式 Runtime 状态

| 服务 | 端口 | 结果 |
| --- | ---: | --- |
| B 客服工作台 | 5173 | RUNNING，LAN 可访问 |
| C Admin | 5174 | RUNNING，仅本机运营入口 |
| A AI 服务 | 8000 | RUNNING，`ready=true`、`model_configured=true` |
| C Platform API | 8011 | RUNNING，数据库 revision 0011 |

四服务由同一正式目录、同一 Release 分支启动，`runtimeMode=standard`、`networkMode=LAN`，状态记录包含受管 PID 与监听 PID。活动集合为 `test_knowledge_v031`，发布后共 `50` chunks（历史 47 + 本次商品 3）；`documents` 仍为 0，不作为活动集合。

## 8. 正式业务 Smoke

验收商品：`(限量特价/袋装)机关山洞螺旋升降5机关/送2飞龙`  
商品 ID：`C-PRODUCT-0ff808af95ce419db9be49427f1c4813`

### Case 1：查看状态

Admin 正确展示三个独立状态：商品知识 `APPROVED`、客服 `DISABLED`、AI 知识 `NOT_GENERATED`。

### Case 2：发布 AI 知识

发布完成后：

- 状态：`PUBLISHED`
- chunks / embeddings：`3 / 3`
- publication receipt：`RAG-0b5a7648cd1fdb836678c9790c439e32`
- fingerprint：`539390be6469fc89d47f21e36a3ccc5ddacbc94803164a73a8ff851418ff3916`

发布只增量写入当前商品的规范文档，没有全量重建 RAG。

### Case 3：启用客服

Admin 批量启用 1 个已审核商品，生成 activation receipt：

`ACT-5cc49873fd6e4d52a36f21ebefc96292`

商品变为 `ENABLED`，B 刷新目录后可见、可选。

### Case 4：客服提问

B 提问“这个商品适合几岁？主要是什么材质？”，A 回答包含 ABS 塑料、5 岁及以上和小零件安全限制。展开依据得到 3 条 `product-knowledge:C-PRODUCT-0ff808af95ce419db9be49427f1c4813` 来源，未混入其他商品。

B 仍保持 `SUGGESTION_ONLY`、`AUTO_SEND_DISABLED`，未自动发送、退款或执行业务动作。

### Case 5：知识变化与恢复

通过现有 R009 浏览器导入与审核链路临时修改一项正式商品知识：

- fingerprint 从 `539390...` 变化为 `7e029b...`
- AI 状态自动进入 `NEED_RESYNC`
- 已发布的 3 个旧 chunks 保持不变，没有自动重发

随后通过同一 R009 浏览器链路把该字段恢复为原值，并重新发布；最终正式商品内容、fingerprint 和 `PUBLISHED / 3 chunks` 均恢复。临时变化从未发布到 RAG。两次审核批次作为正式审计证据保留：

- 变化批次：`251ef1db-781b-49cb-9651-a21e62a16fc0`
- 恢复批次：`fb87ed6d-8545-454d-8143-741686ef5372`

## 9. 发布后数据状态

- Store：2
- Product：24
- SKU：18
- AI publication：1
- publication receipt：1
- activation receipt：9
- 活动集合 chunks：50
- 验收商品：`APPROVED + ENABLED + PUBLISHED`

另外保留 1 条通用知识资料审核记录用于 UI 回归。其 `APPROVED_FOR_ANALYSIS` 只表示进入受控质量分析，不写入 R009 正式商品字段，也不触发 RAG 发布或客服启用。

## 10. 回滚方案

若发布后出现不可接受故障：

1. 先保存当前 0011 数据库、RAG 目录、Runtime manifest 和日志证据，禁止覆盖现状后再调查。
2. 按 `Admin → B → A → C API` 停止正式服务。
3. 将代码恢复到上一正式锚点 `b7783f759776ecf7592ae198893ba5100d75be08`。
4. 不对正式库直接执行 Alembic downgrade；用上述 `standard-platform.0010.offline.sqlite3` 原子恢复数据库。
5. 用 `rag-vector-db.0010.offline` 恢复 RAG，并复核 manifest SHA256；禁止全量重建代替回滚。
6. 按 `C API → A → B → Admin` 启动，验证数据库 0010、活动集合 47 chunks、四服务健康和 B 目录。

数据库和 RAG 必须作为同一回滚单元恢复，不能只回退其中一个。

## 11. 剩余风险

- 其余既有商品尚未全部生成新的 publication receipt；运营应按需增量发布，不应全量自动发布。
- C Admin 仍是内部受控运营界面，正式 RBAC 不属于本次范围。
- 本次 Smoke 证明指定商品的正式闭环，不替代 R003 全量 Pilot 业务验收或 R005 Customer Feedback Loop 真实运行验证。
- R009 审核批次和通用知识审核记录属于审计数据，不应为“清理测试痕迹”而直接删除。

## 12. Gate

```text
R006_1_PRODUCTION_RELEASE_COMPLETE
```

下一入口为 R003 正式 Pilot 业务结果验收；不得把本次发布扩展为 ERP、自动外部同步、全量 RAG 重建或自动客户动作。
