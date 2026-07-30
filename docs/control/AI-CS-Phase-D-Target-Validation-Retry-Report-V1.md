# AI-CS Phase D Target Validation Retry Report V1

> 需求：R008 AI-CS Project Structure Simplification V1
>
> 阶段：Phase D — Target Validation Test Retry
>
> 执行日期：2026-07-30
>
> Target：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`
>
> Target源码：`control/r008-physical-migration-v1@26f8cde1e8f7373315baa1ac68d02f7823b4de82`
>
> 最终Gate：`PASS / TARGET_VALIDATION_PASS / PHASE_E_ENTRY_READY / PHASE_E_NOT_EXECUTED`

## 1. 执行结论

Phase D完整重试通过。

A import smoke和完整pytest、C完整pytest收集与执行、C隔离Alembic往返、B Vitest/typecheck/build、Admin Vitest/typecheck/build，以及contracts 0.2.0/全部schema验证均为exit 0。

上一次失败的唯一P0差异已关闭：C Platform Backend从不兼容的Python 3.11.9环境切换为Phase D2重建的Python 3.12.13环境。同一冻结源码不再在`knowledge_materials/service.py:144`发生SyntaxError；C本轮实际收集95项测试并全部执行通过。

本轮没有修改代码、UI、contracts、requirements、lockfile、Source Tag或数据库，没有启动Target服务、切换Runtime或进入R006。所有临时SQLite、构建、测试树、日志和Vitest缓存已清理；Target继续为原HEAD/Tree且clean，Recovery四服务与SQLite保持不变。

Phase E判定：**从Phase D验证角度允许申请进入，但必须取得新的明确授权；本轮没有执行Phase E。**

最终状态：`TARGET_VALIDATION_PASS`。

## 2. 与失败版Phase D的差异

| 项目 | 失败版Phase D | 本次Retry | 判断 |
| --- | --- | --- | --- |
| Target Branch/HEAD | `control/r008-physical-migration-v1@26f8cde...` | 完全相同 | 源码未变化 |
| Target Tree | `9940eb270e340f6e47c325be28a57979e35c0c39` | 完全相同 | 冻结tree未变化 |
| C Python | `3.11.9` | `3.12.13` | **唯一批准环境变化** |
| C pytest | conftest导入时SyntaxError；exit 4；0项执行 | 95项收集、95项执行；exit 0 | P0关闭 |
| C Alembic | 隔离往返PASS | 隔离往返PASS | 保持通过 |
| A/B/Admin/contracts | PASS | 重新全量执行并PASS | 未沿用历史结果 |
| Recovery | 原四服务与数据未变化 | 原四服务与数据仍未变化 | Runtime未切换 |

本轮没有修改失败源码来适配Python 3.11，也没有修改requirements或重新生成Source Freeze。修复只来自Phase D2批准的Target C venv重建。

## 3. 验证基线与环境

| 项目 | 实际值 |
| --- | --- |
| Target Branch | `control/r008-physical-migration-v1` |
| Target HEAD | `26f8cde1e8f7373315baa1ac68d02f7823b4de82` |
| Target Tree | `9940eb270e340f6e47c325be28a57979e35c0c39` |
| Source Tag解析 | `ai-cs-monorepo-source-freeze-v1` → `26f8cde...3b4de82` |
| A Python / pytest | `3.11.9 / 8.4.2` |
| C Python / pytest | `3.12.13 / 9.1.1` |
| Node.js / npm | `22.23.1 / 10.9.8` |
| pnpm | `11.9.0` |
| Contracts | `0.2.0` |
| 执行平台 | Windows PowerShell，Asia/Shanghai |

执行前Target clean。以下7项冻结输入SHA-256已在执行前记录，并在清理后逐项验证完全一致：

- `backend/requirements.txt`
- `platform_backend/requirements.txt`
- `frontend/package.json`
- `frontend/package-lock.json`
- `admin_web/package.json`
- `admin_web/pnpm-lock.yaml`
- `contracts/version.json`

## 4. 隔离与安全控制

仓库外临时根：

```text
C:\Users\EDY\AppData\Local\Temp\ai-cs-phase-d-retry-815e2e6183ad40d8b7ad58f459af4587
```

隔离规则：

- A的`LOG_DIR`、`KNOWLEDGE_BASE_PATH`、`VECTOR_DB_PATH`全部指向该临时根内的空目录。
- A的`RUN_REAL_RAG_E2E=0`、`RUN_REAL_FEEDBACK_ANALYSIS_E2E=0`、`PLATFORM_API_BASE_URL`为空；没有调用模型、Recovery C或真实RAG数据。
- A/C均设置`PYTHONDONTWRITEBYTECODE=1`，pytest使用外部`--basetemp`与`-p no:cacheprovider`。
- C pytest的全局`DATABASE_URL`指向外部`c-pytest-global.sqlite3`；测试fixture实际使用独立内存SQLite。
- C Alembic使用另一份全新`c-migration.sqlite3`，从不存在状态开始。
- C资料存储显式指向外部`c-storage`。
- B和Admin build直接输出到外部`frontend-dist`、`admin-dist`，没有生成Target内默认`dist`。
- 未运行dev server、uvicorn、Vite preview或任何监听命令。

RAG保护：Target既有`backend/knowledge_base`目录LastWrite UTC执行前后均为`2026-07-30T02:41:42.5080908Z`；Target既有`backend/vector_db`不存在，测试只使用外部空向量路径。本轮没有读取、清空、重建或覆盖真实知识/向量资产。

## 5. 全量测试结果

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| A import smoke | PASS | `app.main:app`导入成功；28条路由；包含`/api/health` |
| A pytest | PASS | `101 passed / 3 skipped / 39 warnings` |
| C pytest收集 | PASS | 15个测试文件组；`95 collected`；exit 0 |
| C pytest执行 | PASS | 95项全部完成；exit 0；1条既有Starlette弃用warning |
| C Alembic往返 | PASS | 新临时SQLite：`0008 → 0007 → 0008` |
| B Vitest | PASS | `28 files / 115 tests` |
| B typecheck | PASS | `vue-tsc --noEmit` |
| B build | PASS | Vite 5.4.21；1704 modules；外部3文件/1,596,811 bytes |
| Admin Vitest | PASS | `25 files / 54 tests` |
| Admin typecheck | PASS | `vue-tsc --noEmit -p tsconfig.json` |
| Admin build | PASS | Vite 6.4.3；146 modules；外部16文件/440,796 bytes |
| Contracts | PASS | `0.2.0`；7个JSON Schema有效 |

合计自动化测试：`365 passed / 3 skipped`。3项skip均为A明确关闭的真实模型、真实RAG或跨C服务opt-in E2E；它们不影响本轮冻结代码回归PASS，也不被伪装为真实模型验收。

## 6. 命令、时间与退出码

以下时间均为`2026-07-30 +08:00`。

| 开始时间 | 工作目录 | 命令摘要 | 用时 | Exit |
| --- | --- | --- | ---: | ---: |
| 11:43:49 | `backend` | `.venv/Scripts/python.exe -c "from app.main import app; ..."` | 1.986s | 0 |
| 11:44:01 | `backend` | `.venv/Scripts/python.exe -m pytest -q --basetemp <external> -p no:cacheprovider` | 6.260s | 0 |
| 11:44:19 | `platform_backend` | `.venv/Scripts/python.exe -m pytest -q --basetemp <external> -p no:cacheprovider` | 5.878s | 0 |
| 11:45:05 | `platform_backend` | `.venv/Scripts/python.exe -m alembic upgrade/current/downgrade/current/upgrade/current` | 3.685s | 0 |
| 11:45:20 | `frontend` | `npm.cmd run test` | 6.677s | 0 |
| 11:45:34 | `frontend` | `npm.cmd run typecheck` | 3.822s | 0 |
| 11:45:47 | `frontend` | `npm.cmd run build -- --outDir <external>` | 4.232s | 0 |
| 11:46:01 | `admin_web` | `pnpm.cmd run test` | 5.201s | 0 |
| 11:46:14 | `admin_web` | `pnpm.cmd run typecheck` | 2.468s | 0 |
| 11:46:26 | `admin_web` | `pnpm.cmd exec vite build --outDir <external>` | 1.810s | 0 |
| 11:46:37 | Target根 | Backend Python读取0.2.0并校验7个Schema | 0.200s | 0 |

C另执行`pytest --collect-only -q`，精确确认15个文件组共95项，exit 0。

## 7. C环境变化与验证

| 项目 | D2前 | 本次Retry |
| --- | --- | --- |
| Python | `3.11.9` | `3.12.13` |
| pip check | 原环境通过但源码不可解析 | 新环境通过 |
| `service.py:144` | SyntaxError | 正常导入、收集和测试 |
| requirements SHA-256 | `73A11B...B986` | 完全相同 |
| Source HEAD/Tree | `26f8cde... / 9940eb2...` | 完全相同 |

C完整pytest不再依赖历史Recovery `95 passed`证据；本次结果来自Target自己的3.12.13 venv和当前冻结tree。

Alembic迁移库最终大小为548,864 bytes，最终revision为`0008_customer_feedback_loop_v1 (head)`；清理前已记录，随后删除。C pytest全局文件SQLite未被创建，fixture使用内存SQLite。

## 8. Warnings与持续风险

非阻断warning：

- A：39条既有httpx TestClient弃用warning。
- C：1条Starlette TestClient/httpx弃用warning。
- B：Vite CJS Node API弃用、测试Vue Router no-match提示、VueUse PURE注释处理、大于500 kB chunk。
- B/Admin：外部outDir不在项目根，Vite明确不自动清空；本轮目录执行前为空且结束后统一删除。

持续治理风险：

- Python requirements仍是范围约束，不是不可变传递哈希锁。
- B冻结依赖树的既有13项漏洞风险未在本轮修复；禁止在验证任务现场升级。
- 本轮不运行真实模型/RAG、浏览器或Target服务，不能替代Phase E运行身份、代理、数据路径和浏览器验收。
- 代码迁移不迁移业务数据；Recovery数据路径治理和回滚仍必须在Phase E中单独验证。

以上风险不否定Phase D冻结代码质量Gate，但继续限制Production/Runtime声明。

## 9. 临时产物与清理

清理前外部临时根包含130个文件、6,945,934 bytes，覆盖：

- A空知识/向量/日志与pytest树；
- C pytest树、资料存储和548,864-byte迁移SQLite；
- B 3个build文件；
- Admin 16个build文件。

清理后：

- 本轮外部`ai-cs-phase-d-retry-*`精确目录不存在；
- `frontend/node_modules/.vite`和`admin_web/node_modules/.vite`本轮缓存已删除；
- Target无`.runtime`、`platform.db`、pytest cache或默认dist；
- A/C源码目录没有本轮新增`__pycache__`；
- 四个Phase C依赖目录继续保留且被Git忽略；
- Target `git status --short`为空，`git diff --check`通过。

## 10. Runtime保护结果

| 服务 | Recovery listener PID | 测试后状态 |
| --- | ---: | --- |
| 5173 B | `33360` | 原PID；HTTP 200 |
| 5174 Admin | `38224` | 原PID；HTTP 200 |
| 8000 A | `24844` | 原PID；HTTP 200 |
| 8011 C | `44428` | 原PID；HTTP 200 |

Recovery继续为`cbc77ed883cb99e2eff76ccb8eb3193bbddaba38`且tracked clean。Recovery SQLite仍为733,184 bytes，LastWrite UTC仍为`2026-07-29T15:32:41.2330435Z`。

没有停止、启动、重启或替换任何服务，没有让Target连接Recovery数据库，也没有修改Recovery venv、运行记录、知识或向量。

## 11. Phase E入口判定

判定：`YES / PHASE_E_ENTRY_READY`，但`PHASE_E_NOT_EXECUTED`。

本次Phase D已满足测试入口条件，可以由用户另行授权Phase E Runtime Migration。Phase E必须重新建立并验证：

1. Target服务启动前的Recovery回滚锚点和用户占用检查；
2. 5173/5174/8000/8011的受管停止、启动、PID、工作目录、解释器和SHA身份；
3. 数据库、知识、向量和运行记录的数据路径策略，禁止重建或清空业务数据；
4. 四项health、固定代理和必要浏览器功能保护验收；
5. 失败时恢复Recovery原运行来源的演练证据。

本报告不构成Phase E执行授权，不表示Target已运行、已切换或已具备Production Readiness；旧目录归档、Worktree退役和R006仍未授权。

最终状态：`TARGET_VALIDATION_PASS`
