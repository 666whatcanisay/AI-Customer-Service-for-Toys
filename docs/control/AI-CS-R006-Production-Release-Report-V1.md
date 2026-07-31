# AI-CS R006 Production Release Report V1

日期：2026-07-31

发布任务：R006 Customer Available Catalog Production Release V1

最终状态：`R006_PRODUCTION_RELEASE_COMPLETE`

## 1. 发布结论

R006 Customer Available Catalog 已从受控 Release 分支部署到正式 AI-CS Runtime。正式 C 现在负责 `data_source`、`customer_service_status`、activation receipt 和最终客服可用目录投影；正式 B 只消费 `/api/v1/customer-service/catalog/**`，不再判断旧测试字段。A、RAG、Prompt、R009 业务逻辑和 Import Center 均未修改。

发布代码 SHA：`b66506ab7706113df5207182d326f1cf03b40726`

发布分支：`release/r006-customer-available-catalog-v1`

来源 Runtime：`42bafcf6630ccbcd1c2dd1d55cb7d3fe735cb1e2`

R006 来源：`feature/r006-customer-available-catalog-v1@bebd27d53af8399717394e71e117762a5d000d1a`

Release tree 与 R006 Feature tree 完全一致；Release 相对正式基线的 A `backend/**` 和 `scripts/**` tree 无差异，R009 专属实现相对候选无差异。共享 contracts 为 additive `0.3.0`，既有 `0.2.0` schema 保留。

## 2. 正式数据库备份

正式数据库：`.runtime/phase-e/data/standard-platform.sqlite3`

发布前先执行在线备份，再在四服务受控停止后生成最终离线回滚快照。最终回滚快照为：

- 路径：`.runtime/phase-e/green-standard/pilot-backups/platform-20260731-093655.sqlite3`
- 大小：`733184` bytes
- SHA-256：`7A90671B0419CB9672C8B3E2488C0E8AD2E241E8849E572F772094AA7EF29B85`
- Alembic revision：`0008_customer_feedback_loop_v1`
- SQLite `PRAGMA integrity_check`：`ok`
- 表数量及各表行数：与备份源一致

补充在线快照：`.runtime/phase-e/green-standard/pilot-backups/platform-20260731-093551.sqlite3`，其大小、SHA-256、revision 和完整性结果与最终离线快照一致。

## 3. 数据库迁移结果

正式服务停止后，使用 Release 代码和正式数据库 URL 执行：

```text
0008_customer_feedback_loop_v1
  -> 0009_product_knowledge_import_v1
  -> 0010_customer_available_catalog_v1
```

结果：

- 当前 revision：`0010_customer_available_catalog_v1`
- 迁移后 `PRAGMA integrity_check`：`ok`
- 迁移后数据库 SHA-256：`A7934A23E917C74013FD6D058084A3C2A8350D9CBE770D67A783EDD8C64A6427`
- 所有 0008 既有业务表行数保持不变
- R009 五张导入相关表均存在；正式库原有 `import_batches=0`、`import_rows=0`，迁移后仍为零，没有伪造或复制验收数据
- R006 初始化完成一次：`catalog_activation_initializations=1`、`activation_receipts=7`
- 来源初始化结果：历史 TEST Store `1 ENABLED`、历史 TEST Product `5 ENABLED`；新 PILOT Store `1 DISABLED`；未知/冲突记录 `0`；PILOT Product 自动启用 `0`
- 初始化策略：`legacy-compat-control-v1.1@1fccb41`

本次没有修改 0009 migration 或 R009 业务逻辑；0009 仅作为已冻结的 0010 前置 migration 被顺序部署。

## 4. 四服务 Runtime 状态

正式目录：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`

以下 PID 是首次发布切换后的运行采样；docs-only 交接提交完成后，官方生命周期脚本会重新签发最终 Git HEAD，因此最终进程 PID 以实时 `status_lan_ai_customer_service.ps1` 输出为准，不把易变 PID 固化为长期身份。

| 服务 | 地址 | 首次 Managed PID | 首次 Listener PID | 状态 |
| --- | --- | ---: | ---: | --- |
| B 客服 | `192.168.1.11:5173` | 38296 | 38296 | RUNNING / HTTP 200 |
| C Admin | `127.0.0.1:5174` | 15452 | 592 | RUNNING / HTTP 200 |
| A AI | `127.0.0.1:8000` | 20100 | 39992 | RUNNING / ready |
| C API | `127.0.0.1:8011` | 33012 | 28536 | RUNNING / health 200 |

发布切换时四项运行记录均指向正式目录和发布代码 SHA，工作树 clean，`runtimeMode=standard`、`networkMode=LAN`。本报告形成 docs-only 交接提交后，使用官方生命周期脚本重新签发最终 Git HEAD；受保护的业务 tree 必须继续与 `b66506a` 相同。数据库 revision 为 0010。A 保持 `ready=true`、`model_configured=true`，活动 collection 为 `test_knowledge_v031`、`47 chunks`，模型为 `qwen3.5:9b`。

## 5. Smoke 测试结果

### 5.1 发布前代码 Gate

- contracts：`4 passed`
- C Backend：`110 passed`
- Alembic：单一 head `0010_customer_available_catalog_v1`
- 与 Release tree 相同的候选证据：B `117 passed`，Admin `58 passed`，两端 typecheck/build PASS，隔离浏览器 R006 E2E PASS

### 5.2 正式 Runtime API Gate

- C `/health`：PASS
- A `/api/health`、`/api/status`：PASS；模型 ready/configured
- C catalog stores：schema `pilot-business-catalog.v1.1`，`result=COMPLETE`，仅返回 `1` 个 `TEST + ENABLED` 店铺
- C catalog products：返回该店铺 `5` 个 ENABLED 商品；SKU 路径正常
- B 同源 `/platform-api/api/v1/customer-service/catalog/stores`：与 C 最终投影一致，仅返回 `1` 个店铺
- B `/ai-chat`、Admin `/store-management`、Admin `/knowledge-materials`：HTTP 200
- 正式启动脚本的真实 AI chat smoke：PASS，保持 `SUGGESTION_ONLY` / `AUTO_SEND_DISABLED`

### 5.3 正式浏览器只读 Gate

使用隔离 Chrome headless 会话验证：

- B 客服页面包含 3 个商品选择控件；店铺下拉仅展示 `1` 个 C 投影店铺，选择后展示 `5` 个商品
- C Admin 店铺管理展示 `2` 条原始店铺记录，其中 `1` 条已启用、`1` 条已禁用，并展示对应启用/关闭入口
- 浏览器没有点击启停按钮，没有产生服务器业务写入；首次使用测试身份只保存在临时浏览器上下文
- 本地截图证据：`.runtime/phase-e/green-standard/r006-release-evidence/b-catalog-smoke.png`、`admin-store-status-smoke.png`

## 6. BUG-B-001 修复状态

状态：`FIXED_VERIFIED_PRODUCTION_SMOKE`

正式环境同时保留一条 `PILOT + DISABLED` 店铺和一条 `TEST + ENABLED` 店铺。C 最终投影只返回可用 TEST 店铺，B 页面仍能展示该店铺和 5 个商品，没有再因单条不兼容/不可用数据清空全部目录。根因修复位于 C Provider 与 B 契约消费边界，没有通过修改业务数据、B 本地白名单或旧字段兜底规避。

本次是发布 Smoke，不替代 R003 完整业务验收。R003 仍需另行验证运营真实启用 PILOT Store/Product、receipt、B 可见与再次禁用回滚。

## 7. 回滚方案

若后续发现发布级问题：

1. 使用正式停止脚本按 Admin → B → A → C API 停止当前 Release 服务，并验证四端口释放。
2. 保留当前故障现场、日志和数据库副本，不直接 downgrade 正式业务库。
3. 将正式代码入口恢复到 `stabilization/product-stable-runtime-v1@42bafcf6630ccbcd1c2dd1d55cb7d3fe735cb1e2`。
4. 在服务完全停止时，用最终离线快照 `platform-20260731-093655.sqlite3` 恢复 `.runtime/phase-e/data/standard-platform.sqlite3`，并重新核对 SHA-256、revision=0008 和 `integrity_check=ok`。
5. 使用原标准配置启动 Recovery Runtime，复核四服务、活动 RAG collection 和真实 AI smoke。

恢复快照而不是对正式业务库执行 Alembic downgrade，是本次首选回滚方式；它同时恢复 schema 和发布前数据边界。Recovery 仓库 `AI-CS-pilot-baseline-recovery-v1@cbc77ed883cb99e2eff76ccb8eb3193bbddaba38` 继续作为更早期的物理回滚锚点，不删除。

## 8. 未完成事项与下一入口

- R003：执行正式 Business Data Activation 业务验收；本发布不主动改变 PILOT 店铺/商品状态。
- R005：只有 R003 通过后，才进入真实 Customer Feedback Loop Pilot 验证。
- R007：第二台终端网络访问仍是独立网络 Gate，不属于 R006 代码问题。

发布完成后四服务保持运行，没有自动停止。

最终状态：`R006_PRODUCTION_RELEASE_COMPLETE`
