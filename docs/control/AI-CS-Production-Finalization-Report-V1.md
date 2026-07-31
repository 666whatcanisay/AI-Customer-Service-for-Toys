# 《AI-CS Production Finalization Report V1》

状态：`AI_CS_INTERNAL_PRODUCTION_READY`

正式版本：`AI-CS V1.0.0`

正式引用：`ai-cs-v1.0.0`

发布分支：`release/ai-cs-v1.0.0`

代码基线：

- 正式化主体：`9f2b500dc0d6469a04a6953b7886d65e34412a22`
- 浏览器验收发现并关闭的 P2 文案修复：`9911ba67cef330a7a1b4f03f82de227cbee6982d`
- 防复发测试提交：`0f230c6f50f8b6162c4e52f3b167053e6592c656`

> 本报告提交后，以 annotated tag `ai-cs-v1.0.0` 解析到的提交作为正式 Runtime 身份。报告不写入自身提交 SHA，避免自引用；精确 SHA 由 Git tag、Runtime 记录和状态脚本共同证明。

## 1. 正式化修改列表

### 1.1 UI 正式化

- B 客服端和 C Admin 的运行身份统一为 `AI-CS V1.0.0 / INTERNAL_PRODUCTION_READY` 对应的中文正式文案。
- 移除用户可见的“测试环境、仅供内部验证、禁止真实客户使用、测试工作台、不是正式登录系统”等旧身份提示。
- 保留并强化安全边界：AI 仅生成建议，必须人工确认；不自动发送、不自动退款、不自动补发、不修改订单。
- C Admin 默认隐藏历史测试包和旧导入调试入口；仅在显式 `VITE_ENABLE_TEST_TOOLS=true` 的开发环境中注册这些路由。
- Import Center 定位和六类 Excel 模板保持不变。
- 浏览器验收发现并关闭 [BUG-B-003](bugs/BUG-B-003.md)：B 侧栏残留早期测试文案。

### 1.2 版本与契约

- A、B、C Admin、C API 的产品版本统一为 `1.0.0`。
- Contracts 升级到 `0.5.0`，加性支持 `INITIAL_IMPORT`；既有 `TEST`、`PILOT` 和 0.4.0/0.3.0 消费语义保持兼容。
- 未修改 R006、R006.1、R006.2 的客服启用、知识发布、目录消费或刷新规则。
- 未修改 A 回答逻辑、Prompt、模型选择或 RAG 发布机制。

### 1.3 数据来源正式化

- 新增迁移 `0012_internal_production_finalization_v1`。
- 仅将具备 `IMPORTED_TEST_ONLY + 0.3.1-test` 原始证据的历史初始化 Store 当前来源由 `TEST` 标记为 `INITIAL_IMPORT`。
- 新增 `catalog_source_formalizations` 审计记录，保留原始来源、包 ID、原始导入状态、原始 schema 版本、迁移版本和时间。
- Product/SKU 继续继承 Store 来源，不进行批量重写。
- 历史 activation receipt 中的 `data_source=TEST` 不回写，作为不可变历史证据。
- 来源标签不参与商品知识 fingerprint，因此本次迁移不触发重新切片、Embedding 或 RAG 发布。

## 2. 数据保护说明

本次未删除、清空或重建以下任何资产：

- 业务店铺、商品、SKU 与商品知识；
- R009 导入批次、字段变化与审核记录；
- activation receipt 与 publication receipt；
- Chroma collection、Chunk、Embedding；
- Alembic migration 历史；
- 测试夹具、回归数据和浏览器证据。

正式化审计结果：

- Store：`INITIAL_IMPORT / ENABLED = 1`，`PILOT / ENABLED = 1`。
- Product：17 个 `APPROVED / DISABLED`、2 个 `APPROVED / ENABLED`、5 个历史 `TEST_CONFIRMED / ENABLED`，数量和客服状态未被迁移改变。
- Activation receipt：历史 `TEST / ENABLED = 6`，`PILOT / ENABLED = 3`，`PILOT / DISABLED = 1`，全部保留。
- AI 知识发布：3 个 `PUBLISHED` 商品、9 chunks、9 embeddings、发布收据完整。
- Chroma：活动集合物理名仍为内部历史名 `test_knowledge_v031`，共 56 chunks；`documents=0`。物理集合未重命名，以避免全量重建。

## 3. 测试数据保留策略

- `fixtures`、测试包、浏览器证据、回归数据和开发测试入口继续保留在工程中。
- 正式运营导航默认不展示测试工具入口；开发者必须显式启用 `VITE_ENABLE_TEST_TOOLS=true` 才能访问。
- 数据库内部沿用 `test_catalog_*` 等历史表名。这些是内部持久化兼容层，不是用户可见产品身份；本次不做表级重构。
- 历史 receipt 中的 `TEST` 是审计事实，不能改写成新的来源值。
- tenant、package、source ID 和 RAG metadata 保持原值，避免破坏既有发布范围和引用链。

## 4. 数据库与备份状态

- 正式 revision：`0012_internal_production_finalization_v1`。
- `PRAGMA integrity_check`：`ok`。
- 正式化审计时间：`2026-07-31 08:22:45.629756 UTC`。
- 在线 0012 备份：`.runtime/phase-e/green-standard/pilot-backups/platform-20260731-164903.sqlite3`
  - SHA256：`46282cdf333c79f080bee7df6e56f789044bb938f024242bde9b272cce8da5d8`
- 停服离线 0012 快照：`.runtime/phase-e/green-standard/pilot-backups/ai-cs-v1.0.0-20260731-164903/standard-platform.0012.offline.sqlite3`
  - SHA256：`39bc426db0bab826608efba065a08edaa67ef27a6ed96cf4a96d20a4e1eda4d0`
  - 与停服时正式数据库逐字节一致。
- 隔离重建的 0011 回滚快照：`standard-platform.0011.reconstructed.sqlite3`
  - SHA256：`71558ddfc91b971a886bff9aa9abaef9455f9ff78fb64f579fb02580507fe8b5`
  - 仅对副本执行 downgrade；正式数据库未执行破坏性 downgrade。
- RAG 离线快照：`rag-vector-db.0012.offline`
  - 5 个文件，1,132,708 bytes；源与副本 manifest 一致。
  - Manifest SHA256：`bbdcbcded050991cbfda91d90dd3887acc93f77a5ae840a65469549230da1a15`。
- 既有 R006.1 的 0010 数据库与 RAG 双快照继续作为更早回滚锚点保留。

说明：0012 已在本轮最终停机快照前完成；因此额外在隔离副本上验证了 `0012 → 0011`，并保留重建后的 0011 快照。正式库未被回退，所有业务记录和 RAG 数据均保持在线状态。

## 5. 服务状态与运行方式

标准入口保持不变，Windows 启停脚本未修改：

```powershell
cd C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS

.\scripts\windows\start_ai_customer_service.ps1
.\scripts\windows\status_ai_customer_service.ps1
.\scripts\windows\stop_ai_customer_service.ps1
```

正式 Runtime：

| 服务 | 端口 | 绑定 | 状态 |
| --- | ---: | --- | --- |
| B 客服工作台 | 5173 | `192.168.1.11` | RUNNING |
| C Admin | 5174 | `127.0.0.1` | RUNNING |
| A AI/RAG | 8000 | `127.0.0.1` | RUNNING / ready |
| C Platform API | 8011 | `127.0.0.1` | RUNNING / health ok |

运行身份：`runtimeMode=standard`、`networkMode=LAN`、Repository root 为唯一项目目录。A 模型 `qwen3.5:9b` 为 ready，C API 版本为 `1.0.0`。

## 6. 回归结果

### 6.1 自动测试

- A Backend：109 passed，3 个显式真实环境 E2E skipped；import smoke 通过。
- B Frontend：120 passed；typecheck 通过；production build 通过。
- C Platform Backend：全量 pytest 通过；contracts 专项 5 passed；Alembic `check` 无新增操作。
- C Admin：64 passed；typecheck 通过；production build 通过。
- 0012 隔离迁移：`upgrade → downgrade → upgrade` 通过，商品状态、receipt、publication、chunk/embedding 计数均保留。
- Contracts：版本 `0.5.0`，schema 与兼容测试通过。

### 6.2 浏览器与业务 Smoke

- Admin：店铺管理、商品知识中心、导入中心、AI 问题中心均可访问；正式身份文案正确；测试工具入口不可见；六个模板下载入口保留。
- B：真实选择已启用商品 `C-PRODUCT-0ff808af95ce419db9be49427f1c4813`。
- AI 知识：`PUBLISHED`，publication receipt 有效，页面显示 3 条引用。
- AI 问答：返回适用年龄、ABS 材质与安全注意事项；3 条 citation 均绑定当前商品。
- 安全：返回 `SUGGESTION_ONLY`、`AUTO_SEND_DISABLED`；页面继续明确人工核对、不自动发送、不自动退款、不修改订单。
- C 与 B 同源代理返回相同的 Store、Product、AI 知识状态和 receipt 证据。
- 浏览器证据保存在忽略 Git 的 `.runtime/.../browser-evidence/`，不包含在源码提交中。

## 7. 剩余风险

- R003 仍需单独完成完整业务验收；本次单商品 Smoke 不等价于全部商品、SKU 和运营场景验收。
- R005 真实客服反馈 → 知识优化 → AI 改善闭环仍为 TODO。
- R007 局域网跨 VLAN/公司网络策略仍是外部阻塞；本机和当前 LAN 入口正常不代表所有办公网段均可访问。
- 当前尚无正式 RBAC/SSO；页面身份仅用于内部运营审计，不应误认为企业级认证。
- 前端生产构建存在大 chunk 告警，当前不影响运行，后续应单独立项，不在正式化任务中重构。
- Git `origin` 指向本机历史保护仓库，本次仅创建本地正式提交与 tag，未声称已远程发布。
- Chroma 活动集合物理名含 `test_`，但其内容与发布证据已受保护；重命名需要独立的无损迁移任务，不能在本次正式化中执行。

## 8. 回滚方案

1. 停止当前标准 Runtime，但不删除任何运行数据。
2. 代码切回 `ai-cs-v1.0.0` 之前的受控锚点；R006.2 基线为 `c1baad8dc6d8728d6c777967d4efbf9c7bb76312`。
3. 数据库优先恢复已验证的离线 0012 快照；若必须回到 0011，使用隔离验证的 0011 快照整体恢复，禁止在正式库上直接破坏性 downgrade。
4. RAG 如需恢复，整体恢复同批次 `rag-vector-db.0012.offline`，不得单独删除 collection、Chunk 或 Embedding。
5. 使用未修改的标准 start/status 脚本启动，核对四服务、revision、active collection、chunk 数和模型 ready 后再开放使用。

最终 Gate：`AI_CS_INTERNAL_PRODUCTION_READY`
