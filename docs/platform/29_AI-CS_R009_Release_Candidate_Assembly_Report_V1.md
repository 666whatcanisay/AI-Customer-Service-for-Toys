# AI-CS R009 Release Candidate Assembly Report V1

日期：2026-07-30

任务：R009 Release Candidate Assembly V1

结论：`R009_RELEASE_CANDIDATE_BLOCKED_BROWSER_UNAVAILABLE`

## 1. 发布候选身份

- 正式 Runtime 基线：`4edf131cb341993b12a0143b0388d932b29faf84`
- R009 精确代码锚点：`aacdc07adc401c6972aaa279bb6f55c434a976ad`
- RC Worktree：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-r009-release-candidate-v1`
- RC 分支：`release/r009-product-knowledge-import-v1-rc1`
- 代码合并提交：`b714b1d6954c14eefff061dc8cd841d89315cce4`
- 合并父提交：`4edf131cb341993b12a0143b0388d932b29faf84`、`aacdc07adc401c6972aaa279bb6f55c434a976ad`
- 共享契约：`contracts 0.2.0`，未修改

RC 使用独立 Worktree，从正式 Runtime SHA 直接创建，再以 `--no-ff` 合入精确 R009 锚点。合并无冲突，正式 `AI-CS` 工作目录、运行分支和服务进程均未切换。

## 2. 合入范围

已确认包含：

- C Admin“资料上传与审核”三步页面及 API 客户端；
- `ProductKnowledgeTemplateParser` 与固定字段映射；
- 店铺校验、商品识别、字段级 Merge 和 `ADD/UPDATE/KEEP/NO_CHANGE` 预览；
- 上传、预检、Merge 预览、通过/驳回审核 API；
- `import_change_sets`、`import_field_changes`、`import_review_records` 及既有导入表扩展；
- `0009_product_knowledge_import_v1` migration；
- R009 Backend 与 Admin 回归测试。

从 `4edf131` 到代码合并提交共变更 24 个文件，全部位于 `platform_backend/**`、`admin_web/**`、`docs/platform/**`。以下范围零变更：

- `backend/**`（A/RAG）；
- `frontend/**`、`extension/**`（B）；
- `contracts/**`；
- `scripts/**`（R008 Runtime 能力）；
- `admin_web/src/views/ImportCenterView.vue`；
- Prompt、模型与向量数据。

## 3. 代码验证结果

### C Platform Backend

- 解释器：Python `3.12.13`
- 命令：`python -m pytest -q`
- 结果：`101 passed`
- 数据隔离：测试 fixture 使用内存 SQLite；测试前清除 `DATABASE_URL`，未连接正式数据库
- 非阻塞提示：FastAPI TestClient 依赖产生一条 Starlette/httpx 弃用警告

### C Admin

- pnpm：`11.18.0`
- 依赖：`pnpm install --frozen-lockfile --offline`，195 个包全部从本机内容寻址缓存复用
- Vitest：`25 files / 55 tests passed`
- Typecheck：通过
- Production build：通过，146 modules transformed
- `pnpm-lock.yaml`：未修改

### 静态与边界检查

- `git diff --check`：通过
- `platform_backend/requirements.txt`：未修改
- `admin_web/pnpm-lock.yaml`：未修改
- 测试后 Git：clean
- 未生成 `platform.db` 或 `.runtime/`

## 4. 0009 Migration 静态检查

本任务没有执行 migration，也没有连接正式数据库。

- 文件：`platform_backend/migrations/versions/0009_product_knowledge_import_v1.py`
- SHA-256：`6934c899682d2c34a8fe06d429e36297a287b91df6ce7f75af24f1dce9190ad3`
- AST revision：`0009_product_knowledge_import_v1`
- AST down revision：`0008_customer_feedback_loop_v1`
- `upgrade()`：存在
- `downgrade()`：存在
- Alembic 静态 graph head：`0009_product_knowledge_import_v1`
- 分叉 head：无

## 5. 数据库升级计划（仅计划，未执行）

后续必须在独立授权的发布静默窗口执行：

1. 再次确认正式仓库、RC 最终 SHA、四服务身份和正式库 revision=`0008_customer_feedback_loop_v1`。
2. 冻结运营写入，使用 `backup_target_pilot_data.ps1 -ConfigPath .runtime/phase-e/config/green-standard.local.ps1 -ConfirmBackup` 生成新的最终在线备份；不得把本次预检旧备份当作最终发布备份。
3. 对新备份记录文件大小、SHA-256、`PRAGMA integrity_check=ok` 和 Alembic revision；备份继续留在 Git 忽略目录。
4. 停止正式四服务后，才允许把正式目录切到已核验的 RC SHA。
5. 仅对正式 Platform SQLite 执行一次 `alembic upgrade 0009_product_knowledge_import_v1`，随后确认当前 revision、五类导入表/扩展字段和 R009 路由。
6. 按 C API → A → B → Admin 顺序启动，复核 8011/8000/5173/5174、Runtime SHA、数据库 revision 和 R009 页面。
7. 浏览器验收通过后才可宣布生产接受；RAG 发布和 B 消费不属于 R009。

回滚不能只依赖 `alembic downgrade`。若部署或验收失败，应停止新 Runtime、恢复发布前最终 SQLite 备份，并把运行源码恢复到 `4edf131`；因为已经审核写入的商品知识并不保证能由结构降级语义撤销。

## 6. 浏览器验收环境

- 目标地址：`http://127.0.0.1:5174/`
- HTTP 只读探测：`200 text/html`，369 bytes
- 受控浏览器连接：失败
- 浏览器发现结果：空列表 `[]`
- Chromium 控制会话：未创建
- 页面交互/截图：未执行

HTTP 200 只证明正式 Admin 服务可达，不能证明 Playwright/Chromium 可被控制，也不能替代真实页面验收。依据浏览器控制规范，没有改用独立 Playwright CLI、普通 HTTP 或其他 UI 工具伪造 Gate。

## 7. 正式 Runtime 保护结果

组装前正式 Runtime 仍为：

- 仓库：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`
- SHA：`4edf131cb341993b12a0143b0388d932b29faf84`
- C API 8011、A 8000、B 5173、Admin 5174：全部 RUNNING、health 可用
- `runtimeMode=standard`、`networkMode=LAN`
- 数据库：`0008_customer_feedback_loop_v1`
- A：`ready=true`、`model_configured=true`、活动集合 `test_knowledge_v031=47`

本任务未停止服务、未切换正式分支、未执行 0009、未修改数据库，也未修改 A/B/RAG/Prompt。

## 8. Gate 结论

| Gate | 结果 |
| --- | --- |
| 4edf131 创建独立 RC | PASS |
| 精确合入 aacdc07 | PASS |
| R009 页面/API/Parser/Merge/0009 完整 | PASS |
| 禁止范围零变更 | PASS |
| Backend/Admin/typecheck/build | PASS |
| 0009 静态 migration 检查 | PASS |
| 数据库升级计划 | PASS（仅计划） |
| 受控 Chromium 启动并访问 5174 | BLOCKED |

因此代码发布候选已经组装完成，但用户要求的完整终态 `R009_RELEASE_CANDIDATE_READY` 尚不能宣布。唯一当前阻塞是没有可用的受控 Browser/Chromium 会话。恢复该会话后，只需在本 RC 上补做“可启动、可访问 5174”的浏览器 Gate；不得在此之前执行正式 0009 或 Runtime 切换。
