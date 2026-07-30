# AI-CS Phase D Target Validation Report V1

> 需求：R008 AI-CS Project Structure Simplification V1
>
> 阶段：Phase D — Target Validation Test
>
> 执行日期：2026-07-30
>
> Target：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`
>
> 最终Gate：`FAIL / TARGET_VALIDATION_FAILED / PHASE_E_BLOCKED`

## 1. 执行结论

Phase D已按冻结Target完成A、C、B、Admin和contracts验证。A、B、Admin、contracts以及C的隔离Alembic往返均通过；C Platform Backend完整pytest在测试收集阶段失败，因此本轮整体不能通过。

阻塞证据为：Python 3.11.9解析`platform_backend/app/knowledge_materials/service.py:144`时返回`SyntaxError: f-string expression part cannot include a backslash`，pytest退出码为4。该错误发生在任何测试用例执行前，不能用迁移通过、其他三线通过或历史基线测试结果替代。

本轮没有修改代码、UI、contracts、requirements、lockfile或数据库，没有启动Target服务，也没有占用或替换5173/5174/8000/8011。所有测试临时数据、缓存和构建产物已清理；Target仍为原Branch/HEAD/Tree且tracked clean，Recovery四服务和SQLite保持不变。

最终状态：`TARGET_VALIDATION_FAILED`。不允许进入Phase E Runtime Migration。

## 2. 验证基线与环境

| 项目 | 实际值 |
| --- | --- |
| Target Branch | `control/r008-physical-migration-v1` |
| Target HEAD | `26f8cde1e8f7373315baa1ac68d02f7823b4de82` |
| Target HEAD Tree | `9940eb270e340f6e47c325be28a57979e35c0c39` |
| Contracts | `0.2.0` |
| Python | `3.11.9` |
| A pytest | `8.4.2`，来自`backend/.venv` |
| C pytest | `9.1.1`，来自`platform_backend/.venv` |
| Node.js / npm | `22.23.1 / 10.9.8` |
| pnpm | `11.9.0` |
| 执行平台 | Windows PowerShell，Asia/Shanghai |

执行前Target无tracked或非忽略untracked修改，四个Phase C依赖目录存在且被Git忽略。两个requirements、两个package文件、两个lockfile和`contracts/version.json`的SHA-256均与Phase C报告一致。

## 3. 隔离与安全控制

外部临时根为：

`C:\Users\EDY\AppData\Local\Temp\ai-cs-phase-d-fc6a4704dde84a85b31174907acd300a`

控制措施：

- A测试显式设置外部`LOG_DIR`、`KNOWLEDGE_BASE_PATH`、`VECTOR_DB_PATH`，并设置`PYTHONDONTWRITEBYTECODE=1`。
- A的`RUN_REAL_RAG_E2E`与`RUN_REAL_FEEDBACK_ANALYSIS_E2E`固定为`0`，`PLATFORM_API_BASE_URL`固定为空，不调用模型或旧C服务。
- C pytest使用外部`DATABASE_URL=sqlite:///C:/Users/EDY/AppData/Local/Temp/.../c-pytest-global.sqlite3`；C Alembic使用另一份`c-migration.sqlite3`。
- pytest均使用外部`--basetemp`和`-p no:cacheprovider`；B构建输出直接写入外部`frontend-dist`。
- C Admin的脚本参数转发没有采用外部outDir，第一次构建生成了默认`admin_web/dist`；随后使用`pnpm exec vite build --outDir <external>`完成隔离复验。默认dist与两端Vitest缓存均在结束时精确清理。
- 没有运行dev server、uvicorn、Vite preview或任何会监听标准端口的命令。

## 4. 测试结果总览

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| A import smoke | PASS | `app.main:app`导入成功，28条路由，包含`/api/health` |
| A pytest | PASS | `101 passed, 3 skipped, 39 warnings` |
| C pytest | **FAIL** | conftest导入时命中`service.py:144` SyntaxError；exit 4；0个测试执行 |
| C Alembic往返 | PASS | 新临时库`upgrade head → current 0008 → downgrade -1/0007 → upgrade head/0008` |
| B Vitest | PASS | `28 files / 115 tests passed` |
| B typecheck | PASS | `vue-tsc --noEmit`，exit 0 |
| B build | PASS | Vite 5.4.21，1704 modules；外部产物3文件/1,596,811 bytes |
| C Admin Vitest | PASS | `25 files / 54 tests passed` |
| C Admin typecheck | PASS | `vue-tsc --noEmit -p tsconfig.json`，exit 0 |
| C Admin build | PASS | Vite 6.4.3，146 modules；隔离产物16文件/440,796 bytes |
| Contracts | PASS | `contract_version=0.2.0`；7个JSON Schema通过`validator_for(...).check_schema(...)` |

总体：10项PASS，1项FAIL。Phase D Gate按全项必过规则为FAIL。

## 5. 命令、时间与退出码

以下时间均为`2026-07-30 +08:00`。

| 开始时间 | 工作目录 | 命令摘要 | 时长 | Exit |
| --- | --- | --- | ---: | ---: |
| 11:10:36 | `backend` | `.venv/Scripts/python.exe -c "from app.main import app; ..."` | 5.278s | 0 |
| 11:10:48 | `backend` | `.venv/Scripts/python.exe -m pytest -q --basetemp <external>/a-pytest -p no:cacheprovider` | 6.558s | 0 |
| 11:11:04 | `platform_backend` | `.venv/Scripts/python.exe -m pytest --basetemp <external>/c-pytest -p no:cacheprovider` | 3.578s | **4** |
| 11:11:18 | `platform_backend` | `.venv/Scripts/python.exe -m alembic upgrade head/current/downgrade -1/current/upgrade head/current` | 4.074s | 0 |
| 11:11:44 | `frontend` | `npm run test` | 7.356s | 0 |
| 11:11:56 | `frontend` | `npm run typecheck` | 3.996s | 0 |
| 11:12:07 | `frontend` | `npm run build -- --outDir <external>/frontend-dist` | 4.283s | 0 |
| 11:12:21 | `admin_web` | `pnpm run test` | 5.526s | 0 |
| 11:12:34 | `admin_web` | `pnpm run typecheck` | 2.663s | 0 |
| 11:12:43 | `admin_web` | `pnpm run build -- --outDir <external>/admin-dist` | 4.273s | 0 |
| 11:12:56 | `admin_web` | `pnpm exec vite build --outDir <external>/admin-dist` | 2.040s | 0 |
| 11:13:13 | Target根 | Backend venv Python读取0.2.0并校验7个Schema | 0.244s | 0 |

## 6. 详细结果

### 6.1 A Backend

Import smoke只创建外部空日志文件，没有进入FastAPI lifespan、加载RAG、模型或向量集合。完整pytest通过；3项skip均为明确关闭的真实RAG/模型或跨C服务E2E：

- `test_real_feedback_analysis_e2e.py`
- `test_real_rag_e2e.py`
- `test_real_scoped_rag_e2e.py`

39条warning均为既有httpx TestClient弃用提示，不影响本次PASS，但不构成生产兼容认证。

### 6.2 C Platform Backend

完整pytest未进入用例执行。失败栈：

```text
platform_backend/app/knowledge_materials/service.py:144
return f"sha256:{hashlib.sha256(canonical + b'\x00' + content).hexdigest()}"
SyntaxError: f-string expression part cannot include a backslash
```

独立Alembic验证使用新建临时SQLite，最终revision恢复为`0008_customer_feedback_loop_v1 (head)`；往返库大小为548,864 bytes，随后删除。迁移通过只证明migration graph在该环境可往返，不能证明C应用可import或pytest可运行。

### 6.3 B Frontend

Vitest、typecheck和build全部通过。保留既有非阻断提示：Vite CJS Node API弃用、测试中的Vue Router no-match warning、VueUse PURE注释处理以及单个JavaScript chunk超过500 kB。

### 6.4 C Admin

Vitest、typecheck和build全部通过。`pnpm run test`只确认lockfile仍符合本地供应链策略且依赖已是up-to-date，没有修改package或lockfile。构建脚本的参数转发行为导致一次默认dist，已如实记录并清理；隔离build复验通过。

### 6.5 Contracts

`contracts/version.json`为`0.2.0`。以下7个Schema均可由其声明的JSON Schema validator检查：

- `ai-control-center-product.schema.json`
- `ai-interaction-event-create.v1.schema.json`
- `ai-interaction-event-receipt.v1.schema.json`
- `assistant-request.schema.json`
- `assistant-response.schema.json`
- `feedback.schema.json`
- `knowledge-publish.schema.json`

没有修改schema、version、CHANGELOG或兼容说明。

## 7. 失败项与风险项

### P0：C源码与Phase C Python运行环境不兼容

当前冻结源码不能被Phase C复现的Python 3.11.9解析。实施前必须先由Control/OPS/C明确并冻结C Platform Backend的批准Python版本，再决定：

1. 若批准运行版本本应支持现有冻结源码，则在不改源码和依赖声明的独立阶段重建对应venv并完整重跑Phase D；或
2. 若必须支持Python 3.11，则另立并授权代码兼容任务，完成审查后重新形成Source Freeze和后续Gate。

本报告不选择方案、不修改源码，也不把历史其他Python环境下的95 passed借作Target证据。

### 持续风险

- B冻结依赖树仍有13项已知漏洞：4 moderate、8 high、1 critical；本轮未执行audit fix。
- Python requirements包含范围而非完整传递哈希锁，Phase C只能证明当次解析安装。
- B大chunk、Vite/TestClient弃用warning仍存在；本轮禁止现场优化或升级。
- Admin build脚本对外部outDir的参数转发不稳定；本轮已通过直接隔离bundler复验并完成清理，后续测试编排应继续显式检查输出位置。

## 8. 临时产物与清理

清理前外部临时区包含：A pytest临时树105文件/4,343,336 bytes、B build 3文件/1,596,811 bytes、Admin build 16文件/440,796 bytes、C迁移SQLite 548,864 bytes，以及两个A测试日志文件。C pytest因收集失败，没有创建全局测试SQLite或资料存储。

清理完成后：

- 外部`ai-cs-phase-d-*`目录不存在；
- Target无`.runtime`、`platform.db`、pytest cache、`frontend/dist`、`admin_web/dist`或两端`.vite`缓存；
- 源码目录外无新增`__pycache__`；
- 四个Phase C依赖目录保留，未作为测试临时产物删除；
- 7项冻结输入SHA-256与执行前完全一致；
- `git status --porcelain`为空，`git diff --check`通过。

## 9. Runtime保护结果

| 项目 | Phase D结束状态 |
| --- | --- |
| Recovery根 | `AI-CS-pilot-baseline-recovery-v1`，未切换 |
| Recovery SHA | `cbc77ed883cb99e2eff76ccb8eb3193bbddaba38`，tracked clean |
| 5173 / 5174 / 8000 / 8011 | 原PID `33360 / 38224 / 24844 / 44428`；全部HTTP 200 |
| Recovery SQLite | 733,184 bytes；LastWrite UTC仍为`2026-07-29T15:32:41.2330435Z` |

没有停止、启动、重启或替换服务，没有读取Recovery SQLite业务内容，也没有让Target连接该数据库。

## 10. Phase E入口判定

判定：`NOT ALLOWED`。

解除条件：

1. 明确并冻结C Platform Backend批准Python版本；
2. 在该批准环境中重新完成依赖复现证据；
3. C完整pytest必须实际收集并全部通过；
4. A/C/B/Admin/contracts全套Phase D在同一Target HEAD上重新复核；
5. Target继续clean、临时产物清理、Recovery不变；
6. 形成新的Gate报告并取得Phase E单独授权。

在此之前禁止Phase E运行迁移、Target服务启动、标准端口切换、Recovery数据连接或旧目录处理；R006仍不得进入。

最终状态：`TARGET_VALIDATION_FAILED`
