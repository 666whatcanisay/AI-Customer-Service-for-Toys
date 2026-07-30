# AI-CS Phase C Dependency Reproduction Report V1

> 需求：R008 AI-CS Project Structure Simplification V1
>
> 阶段：Phase C — Dependency Reproduction
>
> 执行日期：2026-07-30
>
> Target：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`
>
> 最终Gate：`PASS / DEPENDENCIES_REPRODUCED / PHASE_D_NOT_AUTHORIZED`

## 1. 执行结论

Target已在不修改冻结Git Tree的前提下完成四个组件的依赖安装：

| 组件 | 安装入口 | 结果 |
| --- | --- | --- |
| A Backend | 独立`backend/.venv` + `pip install -r backend/requirements.txt` | PASS |
| C Platform Backend | 独立`platform_backend/.venv` + `pip install -r platform_backend/requirements.txt` | PASS |
| B Frontend | `npm ci` | PASS |
| C Admin Web | `pnpm install --frozen-lockfile` | PASS |

四个依赖目录全部命中既有`.gitignore`，Target tracked状态仍为clean；requirements、package文件、lockfile和contracts前后哈希一致。没有启动服务、运行测试、连接数据库、创建`.runtime`、生成日志或build产物，也没有执行R006。

最终状态：`DEPENDENCIES_REPRODUCED`。

## 2. 执行基线

| 项目 | 值 |
| --- | --- |
| Target Branch | `control/r008-physical-migration-v1` |
| Target HEAD | `26f8cde1e8f7373315baa1ac68d02f7823b4de82` |
| HEAD / Index Tree | `9940eb270e340f6e47c325be28a57979e35c0c39` |
| Contracts | `0.2.0` |
| Phase B Manifest文件数 | 542 |
| 执行前Target状态 | clean；四个依赖目录均不存在 |

本轮没有checkout、merge、pull、commit或修改Target引用。Phase C完成后Target仍保持相同Branch、HEAD和Tree。

## 3. 环境版本

| 工具 | 实际版本 | 来源 |
| --- | --- | --- |
| Python | `3.11.9` | `C:\Users\EDY\AppData\Local\Programs\Python\Python311\python.exe` |
| Backend venv pip | `24.0` | `backend/.venv` |
| Platform Backend venv pip | `24.0` | `platform_backend/.venv` |
| Node.js | `v22.23.1` | WinGet Node 22安装目录 |
| npm | `10.9.8` | Node 22随附`npm.cmd` |
| pnpm | `11.9.0` | Codex bundled fallback `pnpm.cmd` |

没有执行Python、pip、Node、npm或pnpm升级。包管理器提示有更新版本时保持现状。

## 4. 安装结果

### 4.1 A Backend

- 环境：`backend/.venv`，Python 3.11.9。
- requirements安装退出码：0。
- `pip check`：`No broken requirements found.`
- `pip freeze --all`：106项。
- 环境清单SHA-256：`359e2283eb05ed43064b3d37c76d5cace829075d92ed83441cf859183d0ee229`。

直接依赖解析结果：

| 包 | 版本 |
| --- | --- |
| fastapi | 0.104.1 |
| uvicorn | 0.24.0 |
| PyMuPDF | 1.28.0 |
| chromadb | 1.5.9 |
| sentence-transformers | 3.0.1 |
| python-dotenv | 1.0.0 |
| openai | 2.50.0 |
| pytest | 8.4.2 |
| httpx | 0.27.2 |

没有加载模型、下载模型权重、创建Chroma集合、读取知识、执行RAG或import应用入口。

### 4.2 C Platform Backend

- 环境：`platform_backend/.venv`，Python 3.11.9。
- requirements安装退出码：0。
- `pip check`：`No broken requirements found.`
- `pip freeze --all`：32项。
- 环境清单SHA-256：`9f38d0a602d642e8cdd906e449da44f58ca8afb3968fc2baac286a52a9f1edc3`。

直接依赖解析结果：

| 包 | 版本 |
| --- | --- |
| fastapi | 0.141.1 |
| httpx | 0.28.1 |
| pytest | 9.1.1 |
| uvicorn | 0.52.0 |
| SQLAlchemy | 2.0.51 |
| alembic | 1.18.5 |
| openpyxl | 3.1.5 |
| python-multipart | 0.0.32 |

没有import C应用、执行Alembic、创建SQLite或连接任何数据库。

### 4.3 B Frontend

- 命令：`npm ci`。
- 退出码：0。
- 安装：244 packages；`npm ls --depth=0`退出0。
- Target依赖目录：`frontend/node_modules`，被Git忽略。
- 没有执行typecheck、Vitest或build；`frontend/dist`不存在。

冻结依赖审计同时报告13项已知漏洞：4 moderate、8 high、1 critical。根据本阶段“不得升级依赖版本、不得修改lockfile”的限制，没有执行`npm audit fix`或`--force`。这不否定“按冻结lockfile成功安装”的Phase C结论，但在生产发布前必须形成独立安全处置与升级兼容评审，不能将本报告解释为依赖安全认证。

### 4.4 C Admin Web

- 命令：`pnpm install --frozen-lockfile`。
- 退出码：0。
- Lockfile：通过pnpm供应链策略检查；resolution被跳过，复用并安装195 packages。
- `pnpm list --depth 0`退出0；直接dependencies 3项，devDependencies 8项。
- Target依赖目录：`admin_web/node_modules`，被Git忽略。
- 没有执行typecheck、Vitest或build；`admin_web/dist`不存在。

pnpm提示11.9.0存在更新版本，但本轮没有升级。

## 5. Git状态与冻结输入差异

| 文件 | Phase C前SHA-256 | Phase C后 | 结论 |
| --- | --- | --- | --- |
| `backend/requirements.txt` | `3985b30a...5e8` | 相同 | PASS |
| `platform_backend/requirements.txt` | `73a11b42...986` | 相同 | PASS |
| `frontend/package.json` | `2ddc26da...61d5` | 相同 | PASS |
| `frontend/package-lock.json` | `300b32ca...697a` | 相同 | PASS |
| `admin_web/package.json` | `f5984989...b95c` | 相同 | PASS |
| `admin_web/pnpm-lock.yaml` | `665cf6df...f20d` | 相同 | PASS |
| `contracts/version.json` | `5ceb9b5a...7d1` | 相同 | PASS |

最终Git证据：

- `git status --porcelain`为空；
- HEAD Tree与Index Tree仍为`9940eb270e340f6e47c325be28a57979e35c0c39`；
- 排除四个依赖目录后仍为542个冻结文件；
- Git忽略项恰好为`backend/.venv/`、`platform_backend/.venv/`、`frontend/node_modules/`、`admin_web/node_modules/`。

Target没有形成任何新commit。Phase C报告与治理状态记录在Control证据分支，不写入Target，避免改变冻结代码身份。

## 6. 依赖复现精度说明

Node两端由lockfile约束，安装过程中lockfile未变化。Python两个requirements包含`>=`/`<`范围而非完整传递依赖哈希锁：

- 本轮证明这些冻结约束在Python 3.11.9下能够独立解析、安装，并通过`pip check`；
- 两个`pip freeze --all`清单及SHA-256已记录，可作为本次环境身份；
- 本轮不能声称未来任意日期或包索引状态下会解析出完全相同的传递版本；
- 若未来需要严格可重复构建，应另立依赖锁定治理任务，评审兼容性后生成受控lock/constraints，不得在本阶段修改requirements。

该限制不阻塞Phase C的“现有冻结输入可以安装”结论，但会阻塞未经评审的生产级供应链可重复性声明。

## 7. 禁止产物检查

Phase C结束后，Target中以下资产均不存在：

- `.runtime/`；
- `.env`；
- `*.db`、`*.sqlite`、`*.sqlite3`；
- `*.log`或包管理器debug日志；
- `frontend/dist`、`admin_web/dist`、Backend build目录；
- 业务运行记录、知识、向量、模型权重或客户数据。

安装包自身的Python/Node二进制与缓存位于四个被忽略的依赖目录；包管理器共享下载缓存位于仓库外，不是Git资产或运行数据。

## 8. Runtime保护结果

| 项目 | Phase C后状态 |
| --- | --- |
| Runtime根 | `AI-CS-pilot-baseline-recovery-v1`，未变 |
| Runtime SHA | `cbc77ed883cb99e2eff76ccb8eb3193bbddaba38`，clean |
| 5173 / 5174 / 8000 / 8011 | 原listener PID 33360 / 38224 / 24844 / 44428；全部HTTP 200 |
| 受保护SQLite | 原位存在，733,184 bytes；LastWrite仍为`2026-07-29T23:32:41.2330435+08:00` |

本轮未停止、启动、重启或替换任何服务，没有读取数据库内容，也没有令Target连接Recovery数据库。

## 9. 未执行事项

以下事项全部未执行：

- Phase D contracts、Backend、Frontend、Admin或集成测试；
- Alembic upgrade/downgrade、数据库初始化或测试数据库创建；
- 应用import smoke、模型加载、RAG、向量或知识同步；
- Phase E隔离运行、标准端口切换、Pilot运行或服务启停；
- Phase F旧目录、Worktree或运行资产处理；
- 代码、UI、contracts、requirements、package/lockfile修改；
- 依赖版本升级、安全自动修复或R006 Business Data Activation。

## 10. Phase D入口条件

Phase D当前为`NOT_AUTHORIZED`。另行授权前必须复核：

1. Target仍为`control/r008-physical-migration-v1@26f8cde...`且tracked clean。
2. HEAD/Index Tree、7项冻结文件SHA-256与本报告一致。
3. 四个依赖目录仍被Git忽略，两个`pip check`、`npm ls`、`pnpm list`通过。
4. Target仍无`.runtime`、数据库、日志和已有build产物。
5. Phase D的C Backend/Alembic只能使用明确的新建隔离临时SQLite，不得读取或连接Recovery数据库。
6. Phase D不得启动或占用5173、5174、8000、8011，也不得改变现行Recovery服务。
7. npm冻结树的13项漏洞和Python范围依赖必须继续作为已知风险记录；不得在测试阶段现场升级依赖。

最终状态：`DEPENDENCIES_REPRODUCED`
