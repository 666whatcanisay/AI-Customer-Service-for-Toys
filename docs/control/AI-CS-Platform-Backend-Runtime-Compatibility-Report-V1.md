# AI-CS Platform Backend Runtime Compatibility Report V1

> 需求：R008 AI-CS Project Structure Simplification V1
>
> 阶段：Phase D1 — Python Runtime Compatibility Verification
>
> 核验日期：2026-07-30
>
> 冻结源码：`ai-cs-monorepo-source-freeze-v1@26f8cde1e8f7373315baa1ac68d02f7823b4de82`
>
> 运行锚点：`ai-cs-pilot-baseline-v1@cbc77ed883cb99e2eff76ccb8eb3193bbddaba38`
>
> 最终Gate：`PYTHON_RUNTIME_COMPATIBILITY_CONFIRMED / TARGET_C_VENV_REBUILD_REQUIRED / PHASE_E_BLOCKED`

## 1. 结论

冻结C Platform Backend代码的批准运行版本确认为 **Python 3.12.13**。

Target当前`platform_backend/.venv`使用Python 3.11.9，不能解析冻结源码`platform_backend/app/knowledge_materials/service.py:144`，因此该venv不兼容，必须在后续单独授权阶段重建。历史C环境、基线文档、Recovery运行记录和当前8011健康实例一致指向Python 3.12.13；同一冻结文件在3.12.13下可解析，在3.11.9下稳定失败。

本轮只做只读核验，没有修改代码、UI、contracts、requirements、数据库、Source Tag或运行服务，没有创建新Source Freeze，也没有重建venv或重跑Phase D。

最终状态：`PYTHON_RUNTIME_COMPATIBILITY_CONFIRMED`。

## 2. 核验范围与身份

| 对象 | 实际身份 | 状态 |
| --- | --- | --- |
| Target | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS` | `control/r008-physical-migration-v1@26f8cde...`，clean |
| Source Tag | `ai-cs-monorepo-source-freeze-v1` | 解析为`26f8cde1e8f7373315baa1ac68d02f7823b4de82`，未变化 |
| Recovery | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-pilot-baseline-recovery-v1` | `control/pilot-baseline-recovery-v1@cbc77ed...`，tracked clean |
| Target C tree | `236ab010ec6d93fe389c0408b5698cdebd4c6b19` | 与Recovery C tree一致 |
| 失败文件blob | `cb6861f301782dfb02ca17b7ffac0da696e0befb` | Target与Recovery一致 |
| Contracts | `0.2.0` | 未修改 |

Target和Recovery的完整`platform_backend` tree一致，因此此次差异不是“迁移漏文件”或“Source Tag漂移”。

## 3. 当前Python版本

Target的`platform_backend/.venv/pyvenv.cfg`记录：

```text
home = C:\Users\EDY\AppData\Local\Programs\Python\Python311
version = 3.11.9
executable = C:\Users\EDY\AppData\Local\Programs\Python\Python311\python.exe
```

Target C venv实际执行`python --version`同样返回`Python 3.11.9`。本机`py -0p`当前也只登记该系统Python 3.11解释器，因此后续不能使用未限定版本的`python`或`py`创建C venv。

结论：当前Target C Python为`3.11.9`，与冻结源码不兼容。

## 4. requirements与版本声明检查

`platform_backend/requirements.txt`冻结内容为：

```text
fastapi>=0.115,<1
httpx>=0.28,<1
pytest>=8,<10
uvicorn>=0.34,<1
SQLAlchemy>=2.0,<3
alembic>=1.13,<2
openpyxl>=3.1,<4
python-multipart>=0.0.20,<1
```

仓库中没有C专用`.python-version`、`runtime.txt`、`pyproject.toml`、`setup.py`或`setup.cfg`来声明Python范围。requirements只约束Python包，不等于Python解释器版本声明。

同时，范围依赖在两套环境中已出现解析差异：Recovery为FastAPI `0.139.2`、Uvicorn `0.51.0`，Target为FastAPI `0.141.1`、Uvicorn `0.52.0`。两边`pip check`均通过，但这说明后续环境复现必须记录实际包清单；本轮不修改requirements，也不解决依赖锁定问题。

## 5. 历史C环境证据

### 5.1 已有venv

在当前AI-CS资产根下发现8个可识别的`platform_backend/.venv/pyvenv.cfg`：

| Python | 数量 | 代表目录 | 判断 |
| --- | ---: | --- | --- |
| `3.12.13` | 7 | `AI-CS-pilot-baseline-recovery-v1`、`AI-CS-platform-center`、`AI-CS-pilot-baseline-runtime`等 | 历史C主环境 |
| `3.11.9` | 1 | 新Target `AI-CS` | Phase C新建且Phase D收集失败 |

Recovery venv的`pyvenv.cfg`和实际解释器均为Python 3.12.13，`sys.implementation.cache_tag`为`cpython-312`。

### 5.2 文档与测试记录

| 证据 | 记录 |
| --- | --- |
| `docs/platform/baseline/baseline_backend_status.md` | 明确记录Python `3.12.13`及C依赖版本 |
| `docs/platform/baseline/baseline_test_results.md` | Python `3.12.13`独立venv；pytest与真实health通过 |
| `docs/control/AI-CS-Pilot-Baseline-Recovery-Execution-Report-V1.md` | Recovery C Backend `95 passed`，迁移至0008，四服务同SHA运行 |
| 当前Control `machine-context.json`历史verification | C Backend Python `3.12.13`、pytest与`/health`通过 |

A线文档中出现的Python 3.11.9属于A Backend环境，不能据此推断C Platform Backend兼容3.11。

### 5.3 当前运行记录

Recovery `.runtime/platform.json`记录8011从Recovery根启动，命令为：

```text
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011 --no-access-log
```

记录的启动时间为`2026-07-29T15:42:34Z`，运行解释器来自Python 3.12.13基础环境；核验时8011监听进程仍存在，`GET http://127.0.0.1:8011/health`返回HTTP 200、服务名`platform-backend`。

`app.main`会导入知识资料路由及`knowledge_materials/service.py`。因此，同一C source tree在Python 3.12.13下能够被真实运行实例导入，是比静态版本文本更强的历史可用证据。本轮只读取运行身份与health，没有重启或修改服务。

## 6. 源码级兼容性验证

失败行保持冻结：

```python
return f"sha256:{hashlib.sha256(canonical + b'\x00' + content).hexdigest()}"
```

只读`ast.parse`结果：

| 解释器 | 结果 |
| --- | --- |
| Target Python `3.11.9` | FAIL：`f-string expression part cannot include a backslash`，定位line 144 |
| Recovery Python `3.12.13` | PASS：相同blob可解析 |

进一步使用Python 3.12.13对冻结C项目的`app/`、`migrations/`、`tests/`共89个Python源码文件执行只读AST解析，全部通过。AST验证不生成字节码、不导入应用、不连接数据库，也不替代完整pytest。

## 7. Python版本范围判定

| 范围 | 判定 | 说明 |
| --- | --- | --- |
| Python `3.11.x`及以下 | **不批准** | 已由3.11.9对冻结源码的确定性语法失败证实 |
| Python `3.12.x` | **批准窗口** | 该语法从3.12可解析；历史和当前运行均以3.12.13验证 |
| Python `3.13+` | **未验证，不批准用于本次恢复** | 本轮没有安装或测试，不应扩大基线范围 |

从语法角度，冻结源码要求Python `>=3.12`。从可复现的Controlled Pilot角度，本次批准范围冻结为`>=3.12,<3.13`，并以精确版本 **Python 3.12.13** 作为推荐和复验版本。该范围不声称所有3.12补丁版本均已逐一验证。

## 8. 推荐版本与venv处置

推荐：**Python 3.12.13**。

Target C venv需要重建，原因是venv的解释器由创建时固定，不能通过重新安装requirements把3.11.9变成3.12.13。

后续执行约束：

1. 必须取得单独授权后才可处理Target `platform_backend/.venv`；本轮没有执行。
2. 使用显式、经核验的Python 3.12.13可执行文件创建独立Target venv，禁止依赖默认`python`/`py`解析。
3. 不复制Recovery venv，不修改或停止Recovery环境，不连接Recovery数据库。
4. 安装冻结`platform_backend/requirements.txt`，不升级、不改声明；记录实际resolved package inventory并执行`pip check`。
5. venv继续位于Git忽略路径，不得进入Git。
6. 重建前后复核Target HEAD/Tree、Source Tag和冻结输入哈希，确保没有源码或契约变化。

不需要修改Source Tag，也不需要生成新的Source Freeze。当前Source Tag准确保存了已在Python 3.12.13运行过的源码；问题属于Target解释器选择错误。

## 9. 是否允许重新Phase D

判定：**条件允许，但本轮不执行**。

进入完整Phase D复验的前置Gate：

1. 单独授权Target C venv以Python 3.12.13重建；
2. 新venv版本、包清单和`pip check`通过并形成证据；
3. Target仍为`26f8cde...`、Tree `9940eb2...`且clean；
4. requirements、package/lock和contracts冻结输入哈希不变；
5. 完整重跑A/C/B/Admin/contracts矩阵，C pytest必须实际收集并通过；
6. C迁移继续使用隔离临时SQLite；所有临时产物清理；Recovery身份、端口和数据保持不变。

只有新的完整Phase D报告达到`TARGET_VALIDATION_PASS`后，才可以另行申请Phase E。当前Phase E仍为`BLOCKED`。

## 10. 本轮未执行事项

- 未重建、删除或修改任何venv；
- 未运行pytest、Alembic、typecheck或build；
- 未启动、停止或重启Target/Recovery服务；
- 未占用或切换5173、5174、8000、8011；
- 未连接、读取或改写Recovery业务数据库；
- 未修改代码、UI、contracts、requirements、lockfile或Git历史；
- 未修改Source Tag，未生成新Source Freeze；
- 未进入Phase E或R006 Business Data Activation。

最终状态：`PYTHON_RUNTIME_COMPATIBILITY_CONFIRMED`
