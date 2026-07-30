# AI-CS Phase D2 C Backend Environment Rebuild Report V1

> 需求：R008 AI-CS Project Structure Simplification V1
>
> 阶段：Phase D2 — C Platform Backend Virtual Environment Rebuild
>
> 执行日期：2026-07-30
>
> Target：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`
>
> Target源码：`control/r008-physical-migration-v1@26f8cde1e8f7373315baa1ac68d02f7823b4de82`
>
> 最终Gate：`C_BACKEND_RUNTIME_REBUILT / PHASE_D_RERUN_READY / PHASE_E_BLOCKED`

## 1. 执行结论

Target自己的`platform_backend/.venv`已从Python 3.11.9重建为批准版本Python 3.12.13，并使用冻结`platform_backend/requirements.txt`完成依赖安装。

新环境`pip check`返回`No broken requirements found.`；`pip freeze`记录30项，依赖版本集合与旧venv一致。冻结源码`knowledge_materials/service.py`已可由新解释器进行AST解析。requirements SHA-256前后相同，Target继续为原Branch/HEAD/Source Tag且Git clean。

本轮没有修改代码、UI、contracts、requirements、lockfile、Source Tag、数据库或Recovery环境，没有启动Target服务，也没有执行pytest、Alembic或Phase E。

判定：允许在取得单独授权后重新执行完整Phase D；当前不自动开始Phase D，Phase E继续阻塞。

最终状态：`C_BACKEND_RUNTIME_REBUILT`。

## 2. 任务范围与保护边界

| 项目 | 内容 |
| --- | --- |
| 唯一允许变更 | `AI-CS/platform_backend/.venv` |
| C路径Owner | `platform_backend/**` |
| 明确保护 | 代码、UI、contracts、requirements、lockfile、Tag、数据库、Recovery、运行服务 |
| Target Branch | `control/r008-physical-migration-v1` |
| Target HEAD | `26f8cde1e8f7373315baa1ac68d02f7823b4de82` |
| Source Tag解析 | `ai-cs-monorepo-source-freeze-v1` → `26f8cde1e8f7373315baa1ac68d02f7823b4de82` |
| Recovery | `AI-CS-pilot-baseline-recovery-v1@cbc77ed883cb99e2eff76ccb8eb3193bbddaba38` |

执行前已确认：

- venv绝对路径精确为`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS\platform_backend\.venv`；
- 该路径位于Target `platform_backend`根内；
- 没有进程使用Target venv的`Scripts/python.exe`；
- Target Git clean；
- 显式解释器实际版本为Python 3.12.13；
- Recovery C venv仍为Python 3.12.13且不在允许变更范围。

## 3. 原venv状态

| 项目 | 原值 |
| --- | --- |
| Python | `3.11.9` |
| Python来源 | `C:\Users\EDY\AppData\Local\Programs\Python\Python311\python.exe` |
| pip | `24.0` |
| pip freeze数量 | `30` |
| 环境问题 | 不能解析冻结源码`platform_backend/app/knowledge_materials/service.py:144` |

旧环境与Phase D失败报告一致，没有在重建前运行测试或连接数据库。

## 4. 重建方式

使用的唯一基础解释器：

```text
C:\Users\EDY\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
Python 3.12.13
```

没有调用默认`python`或默认`py`。

直接递归删除命令被本机执行安全策略在运行前拒绝，未产生文件变化。随后使用Python标准库的受控重建语义执行：

```text
<explicit-python-3.12.13> -m venv --clear <Target/platform_backend/.venv>
```

`--clear`先清空既有环境目录内容，再以指定解释器重新创建venv，达到删除旧环境内容并重新创建Target venv的目标，同时把操作限制在已核验的单一路径。重建成功，无失败回滚或Recovery介入。

新`pyvenv.cfg`记录：

```text
home = C:\Users\EDY\.cache\codex-runtimes\codex-primary-runtime\dependencies\python
include-system-site-packages = false
version = 3.12.13
executable = C:\Users\EDY\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
command = ...\python.exe -m venv --clear C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS\platform_backend\.venv
```

## 5. requirements安装

安装命令使用新venv自己的解释器：

```text
AI-CS\platform_backend\.venv\Scripts\python.exe -m pip install --disable-pip-version-check --no-input --requirement AI-CS\platform_backend\requirements.txt
```

| 项目 | 结果 |
| --- | --- |
| Install exit | `0` |
| 用时 | `9.971s` |
| 新Python | `3.12.13` |
| 新pip | `25.0.1`，由Python 3.12.13 venv自带；未执行pip升级 |
| `pip check` | PASS：`No broken requirements found.` |
| 依赖升级命令 | 未执行 |
| requirements修改 | 未发生 |

requirements使用版本范围，因而本报告只证明本次实际解析安装结果；严格的长期传递依赖锁定仍属于既有`PM-R03`治理风险。

## 6. pip inventory

规范化`pip freeze`结果为30项，SHA-256为：

```text
ba43c13e6b0c51792568fd55aadadf35a37fe09e22784ed04185aa9d7149c61b
```

完整inventory：

```text
alembic==1.18.5
annotated-doc==0.0.5
annotated-types==0.8.0
anyio==4.14.2
certifi==2026.7.22
click==8.4.2
colorama==0.4.6
et_xmlfile==2.0.0
fastapi==0.141.1
greenlet==3.5.4
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.18
iniconfig==2.3.0
Mako==1.3.12
MarkupSafe==3.0.3
openpyxl==3.1.5
packaging==26.2
pluggy==1.6.0
pydantic==2.13.4
pydantic_core==2.46.4
Pygments==2.20.0
pytest==9.1.1
python-multipart==0.0.32
SQLAlchemy==2.0.51
starlette==1.3.1
typing-inspection==0.4.2
typing_extensions==4.16.0
uvicorn==0.52.0
```

该30项版本集合与重建前`pip freeze`一致。解释器由3.11.9变为3.12.13，pip bootstrap版本由24.0变为25.0.1；没有通过requirements升级业务依赖版本。

## 7. 完整性验证

| Gate | 结果 | 证据 |
| --- | --- | --- |
| 新venv Python | PASS | `Python 3.12.13`，`cache_tag=cpython-312` |
| 显式基础解释器 | PASS | 精确路径与版本断言均通过 |
| pip check | PASS | 无破损依赖 |
| pip freeze | PASS | 30项，inventory SHA-256已记录 |
| 冻结语法烟测 | PASS | 新解释器对`knowledge_materials/service.py`执行只读`ast.parse`通过 |
| requirements哈希 | PASS | 前后均为`73A11B429E3809E3CCC4ED088A4C4894FEA81535D6259D5E3BE986DB9B12B986` |
| Target Git | PASS | 原Branch/HEAD，`git status --short`为空 |
| Source Tag | PASS | 仍解析到`26f8cde...3b4de82` |
| Git忽略 | PASS | `.gitignore:12:.venv/`覆盖新环境 |
| 禁止产物 | PASS | 无`.runtime`、`platform.db`、`.pytest_cache`或`logs` |

AST解析只验证D1失败语法已由批准解释器接受，不替代完整pytest或Phase D验收。

## 8. Recovery保护结果

| 项目 | D2结束状态 |
| --- | --- |
| Recovery SHA | `cbc77ed883cb99e2eff76ccb8eb3193bbddaba38`，tracked clean |
| Recovery C Python | `3.12.13` |
| Recovery C venv cfg SHA-256 | `237B1DBEC09A5EEE9F89F518DC2A4AAA90512E50809890C199EF1962E8AEF1A7`，与执行前一致 |
| 8011 listener | 原PID `44428`，启动时间仍为`2026-07-29 23:42:34 +08:00` |
| 8011 health | HTTP 200，`platform-backend` |

没有停止、启动、重启或替换Recovery服务，没有修改Recovery venv、运行记录、数据库、知识或向量。

## 9. 是否允许重新Phase D

判定：`YES / PHASE_D_RERUN_READY`，但必须取得新的明确授权后执行。

下一轮必须完整执行Phase D，而不是只重跑C：

1. A import smoke与完整pytest；
2. C完整pytest及隔离临时SQLite迁移往返；
3. B Vitest、typecheck、build；
4. Admin Vitest、typecheck、build；
5. contracts 0.2.0与全部schema验证；
6. 临时产物清理、冻结输入哈希、Target clean及Recovery不变复核。

只有完整Phase D达到`TARGET_VALIDATION_PASS`后，才可以另行申请Phase E。D2本身不是运行迁移或生产就绪证据。

## 10. 未执行事项

- 未修改或提交Target源码；
- 未修改UI、contracts、requirements、lockfile或Source Tag；
- 未创建数据库、runtime、日志、缓存或构建产物；
- 未运行pytest、Alembic、typecheck或build；
- 未启动Target服务或占用5173/5174/8000/8011；
- 未修改Recovery环境或业务数据；
- 未进入Phase E或R006 Business Data Activation。

最终状态：`C_BACKEND_RUNTIME_REBUILT`
