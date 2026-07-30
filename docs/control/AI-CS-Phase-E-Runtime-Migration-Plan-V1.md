# AI-CS Phase E Runtime Migration Plan V1

> 需求：R008 AI-CS Project Structure Simplification V1
>
> 阶段：Phase E — Runtime Migration Preparation
>
> 日期：2026-07-30
>
> 性质：规划与只读预检查；不是运行切换授权
>
> 最终Gate：`RUNTIME_MIGRATION_PLAN_READY / RUNTIME_MIGRATION_EXECUTION_NOT_AUTHORIZED / RECOVERY_RUNTIME_UNCHANGED`

## 1. 结论

Phase E运行迁移计划已就绪，推荐采用同机蓝绿两段式切换：

1. Recovery继续占用标准端口并保持Pilot可用；Target先在仅本机可访问的影子端口、独立运行目录和独立数据快照上验证。
2. 影子环境通过后，进入经用户明确授权的短时人工静默窗口；使用Recovery自己的受管运行记录安全停止旧环境，再从Target在标准端口启动四服务。
3. 标准端口验收失败时，只停止已验证的Target进程，直接用原Recovery代码、配置、数据库、知识和向量恢复；不按端口强杀，不删除任何环境。

本轮只完成计划和只读预检查。没有停止或启动任何服务，没有创建Target `.runtime`，没有复制数据库、知识或向量，没有修改代码、UI、contracts、数据库、配置文件或运行记录，也没有执行R006。

## 2. 当前Runtime状态（Blue / Recovery）

### 2.1 运行锚点

| 项目 | 当前事实 |
| --- | --- |
| Repository | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-pilot-baseline-recovery-v1` |
| Branch | `control/pilot-baseline-recovery-v1` |
| SHA | `cbc77ed883cb99e2eff76ccb8eb3193bbddaba38` |
| Git状态 | tracked clean |
| Contracts | `0.2.0` |
| Bind | `127.0.0.1`，LOCAL模式 |

### 2.2 四服务只读核验

2026-07-30使用Recovery正式状态脚本核验：

| 服务 | 标准端口 | 受管PID | 监听PID | 工作目录 | 状态 |
| --- | ---: | ---: | ---: | --- | --- |
| C API | 8011 | 19020 | 44428 | `Recovery/platform_backend` | RUNNING；HTTP 200；SHA/源码身份已验证 |
| A | 8000 | 20384 | 24844 | `Recovery/backend` | RUNNING；HTTP 200；SHA/源码身份已验证 |
| B | 5173 | 33360 | 33360 | `Recovery/frontend` | RUNNING；HTTP 200；SHA/源码身份已验证 |
| C Admin | 5174 | 30732 | 38224 | `Recovery/admin_web` | RUNNING；HTTP 200；SHA/源码身份已验证 |

运行证据同时确认：

- C数据库revision为`0008_customer_feedback_loop_v1`；
- 冻结测试包状态为`IMPORTED_TEST_ONLY`；
- A历史同步为47/47，当前运行时知识统计为`MATCH`、47 chunks；
- A模型`qwen3.5:9b`为configured/ready，初始化错误为空；
- 5174保持loopback-only；
- Recovery数据库为`.runtime/data/pilot-baseline-recovery-platform.sqlite3`，本轮未写入。

## 3. 目标Runtime（Green / Target）

| 项目 | 目标事实 |
| --- | --- |
| Repository | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS` |
| Branch | `control/r008-physical-migration-v1` |
| SHA | `26f8cde1e8f7373315baa1ac68d02f7823b4de82` |
| Tree | `9940eb270e340f6e47c325be28a57979e35c0c39` |
| Git状态 | clean |
| Contracts | `0.2.0` |
| 依赖 | A/C venv、B/Admin node_modules已独立复现且被Git忽略 |
| 当前运行状态 | 未运行；`.runtime`不存在；标准端口均未由Target占用 |

Phase D已在该不变HEAD/Tree上通过完整验证：365 passed、3项显式opt-in skip；这只证明Target源码与依赖可验证，不代表Target已经运行或数据已迁移。

## 4. 迁移不变量

整个Phase E必须保持：

- Recovery目录、Git SHA、忽略配置、SQLite、知识、向量和日志原样保留，直到另行批准Phase F。停止前的运行记录先保存为只读脱敏证据；活动`*.json`只允许Recovery正式stop/start脚本按生命周期删除或重建，不得手工编辑。
- Target只从`26f8cde...`启动；不得从任何dirty Worktree补文件。
- contracts保持`0.2.0`；A测试知识schema保持`0.3.1-test`，不进行合并或升级。
- 数据库不重建、不清空；知识不重新生成；向量不重建。
- 蓝绿环境不得同时写入同一个SQLite、知识资料目录或Chroma目录。
- 切换验收窗口内禁止客服、运营和测试人员产生业务写入。
- 不执行自动发送、自动退款、订单变更、ERP动作、知识发布、模型训练或Prompt修改。

任何一项不变量不满足，执行Gate立即失败并保持/恢复Recovery。

## 5. 运行配置迁移方案

### 5.1 配置载体与密钥边界

Target执行时使用其被Git忽略的`.runtime/phase-e/`作为唯一运行状态根：

```text
AI-CS/.runtime/phase-e/
├── config/
│   ├── green-shadow.local.ps1
│   └── green-standard.local.ps1
├── data/
├── rag/
│   ├── knowledge-base/
│   └── vector-db/
├── knowledge-materials/
├── green-shadow/
│   ├── *.json
│   └── logs/
├── green-standard/
│   ├── *.json
│   └── logs/
└── manifests/
```

以上均不得进入Git。配置文件只能记录路径、端口、bind、模型名和非敏感开关；密钥不从Recovery `.env`复制、不写入报告/日志/Git，应通过当前Windows进程环境或既有受控本机密钥方式重新提供。执行报告只记录变量名和“已配置/未配置”，不得记录值。

### 5.2 配置映射

| 配置域 | Recovery当前值/来源 | Green shadow | 标准端口Target |
| --- | --- | --- | --- |
| `RepositoryRoot` | Recovery根 | Target根 | Target根 |
| `RuntimeDirectory` | `Recovery/.runtime` | `Target/.runtime/phase-e/green-shadow` | `Target/.runtime/phase-e/green-standard` |
| A Python | `Recovery/backend/.venv/...` | `Target/backend/.venv/...` | 同左 |
| C Python | Recovery Python 3.12.13 | Target Python 3.12.13 | 同左 |
| B/Admin依赖 | Recovery各自node_modules | Target各自node_modules | 同左 |
| C `DATABASE_URL` | Recovery SQLite | Target影子SQLite快照 | Target最终静默点SQLite快照 |
| C资料存储 | 当前默认目录；预检未发现文件 | `Target/.runtime/phase-e/knowledge-materials` | 同一Target受控目录 |
| A `KNOWLEDGE_BASE_PATH` | Recovery `backend/knowledge_base` | Target只读快照目录 | Target独立目录 |
| A `VECTOR_DB_PATH` | Recovery `backend/vector_db` | Target独立快照目录 | Target独立目录 |
| A `LOG_DIR` | Recovery本地日志 | Target独立日志 | Target独立日志 |
| `LLM_PROVIDER/MODEL/BASE_URL` | `ollama/qwen3.5:9b/127.0.0.1:11434` | 保持 | 保持 |
| A `PLATFORM_API_BASE_URL` | `127.0.0.1:8011` | `127.0.0.1:18011` | `127.0.0.1:8011` |
| CORS | 5173/5174 loopback origins | 仅15173/15174 loopback origins | 恢复5173/5174 loopback origins |
| B API地址 | 8000/8011 | `VITE_RAG_API_BASE_URL=http://127.0.0.1:18000`；`VITE_PLATFORM_API_BASE_URL=http://127.0.0.1:18011` | 8000/8011 |
| Admin API地址 | 默认同源代理到8000/8011 | 显式`VITE_AI_API_BASE_URL=http://127.0.0.1:18000`；`VITE_PLATFORM_API_BASE_URL=http://127.0.0.1:18011` | 默认代理或显式8000/8011 |
| 自动数据动作 | Recovery `AutoSyncTestKnowledge=true` | `AutoSyncTestKnowledge=false`、`AutoImportTestData=false` | 首次切换仍保持false；只使用已验证快照 |

P0配置规则：影子Admin必须显式注入两个影子API地址。当前`admin_web/vite.config.ts`的默认代理固定指向8000/8011；若省略环境变量，15174页面会连到Recovery后端，形成伪绿色验收。影子运行记录必须把“Admin API目标已显式配置”写入脱敏manifest。

同一执行入口还必须在调用启动脚本前，以当前进程环境显式设置`KNOWLEDGE_BASE_PATH`、`VECTOR_DB_PATH`、`LOG_DIR`和`PLATFORM_KNOWLEDGE_MATERIAL_STORAGE_DIR`的Target绝对路径；既有启动脚本不会从本地配置hashtable自动生成这四项。启动前应记录变量名、路径归属和路径manifest，不记录密钥或业务内容；任一变量缺失或解析到Recovery根都必须中止。

### 5.3 数据库保护

Phase E执行时的数据库流程：

1. 使用Recovery既有`backup_target_pilot_data.ps1 -ConfirmBackup`执行SQLite online backup；不直接复制正在使用的SQLite主文件。
2. 记录源文件大小、备份大小、SHA-256、Alembic revision和只读`PRAGMA integrity_check`结果，不读取或输出业务内容。
3. 将备份物化为Target影子库；影子C只连接该库，绝不连接Recovery路径。
4. 影子验证期间禁止业务写入。
5. 标准端口切换前进入人工静默窗口，安全停止Recovery后再生成最终一致快照；以该最终快照替换尚未开放使用的Target目标库。
6. 对最终Target库重复integrity、revision、文件哈希与表行数不变量检查。任何差异未解释即终止切换。

不迁移Recovery运行记录或日志到Target；Target必须生成自己的受管记录。若切换开放后Target已经产生新业务写入，禁止直接用旧Recovery库覆盖；先冻结写入、备份Target，再由单独的数据协调任务决定回退数据处理。

### 5.4 知识、向量与资料保护

当前Recovery只读资产盘点：

| 资产 | 当前证据 |
| --- | --- |
| `backend/knowledge_base` | 1个文件，124 bytes |
| `backend/vector_db` | 5个文件，1,038,500 bytes；当前运行统计47 chunks MATCH |
| `platform_backend/.runtime/knowledge-materials` | 当前不存在 |

执行时必须：

- 在没有同步/写入动作的稳定点，对源知识与向量生成文件数、总大小、相对路径哈希和文件哈希manifest；不得输出正文。
- 复制到Target独立忽略目录后重新计算manifest，Source/Target必须完全一致。
- 复制前后再次检查Recovery源manifest；发生变化则丢弃Target副本并重新进入稳定点。
- 影子和标准Target都显式使用Target路径，不共享Recovery Chroma目录。
- `AutoSyncTestKnowledge=false`；Phase E不得通过重新同步来掩盖复制不一致，也不得重建向量。
- C资料目录当前为空/不存在不代表永久可忽略；执行前必须再次检查，若出现文件则按同样的manifest和独立路径规则保护。

### 5.5 启停与状态脚本

只使用Target或Recovery各自仓库内的正式脚本：

- `scripts/windows/start_ai_customer_service.ps1`
- `scripts/windows/status_ai_customer_service.ps1`
- `scripts/windows/stop_ai_customer_service.ps1`
- `scripts/windows/backup_target_pilot_data.ps1`

每次调用都必须显式传入对应仓库的`-ConfigPath`。不得依赖当前目录、默认`python`/`py`、默认配置或另一仓库的脚本。停止必须通过受管记录验证PID、监听PID、路径、启动时间、命令特征和端口归属；禁止按端口结束未知进程。

本次迁移保持LOCAL/loopback模式，不借机处理R007或开放LAN、防火墙、5174、8000、8011。

## 6. 蓝绿切换方案

### Stage E0 — 执行前只读Gate

执行前逐项重检：

- Recovery仍为`cbc77ed...`且四服务身份全部已验证；
- Target仍为`26f8cde...`、Tree不变、clean；
- contracts仍为0.2.0；
- Target四套依赖存在，C为Python 3.12.13；
- 标准端口仍只属于Recovery受管实例；
- 影子端口无监听；
- Pilot无正在处理的客服会话、运营写入、反馈提交或资料上传；
- 备份目标空间足够，Recovery/Target数据路径不存在交叉引用；
- 用户已单独授权Phase E执行和静默窗口。

### Stage E1 — Green影子验证（Recovery不停）

推荐影子端口：

| 服务 | 影子端口 | 绑定 |
| --- | ---: | --- |
| C API | 18011 | 127.0.0.1 |
| A | 18000 | 127.0.0.1 |
| B | 15173 | 127.0.0.1 |
| C Admin | 15174 | 127.0.0.1 |

2026-07-30只读扫描时四个影子端口均无监听；执行时必须重新扫描，不能把当前结果当作预留。

影子阶段使用独立数据库、知识、向量、日志和运行记录。Recovery继续在5173/5174/8000/8011运行。影子验证通过后，先用Target影子运行记录安全停止四个影子服务，确认影子端口全部释放；Recovery仍不动。

### Stage E2 — 受管标准端口切换

仅在E1全PASS且用户确认静默窗口后执行：

1. 记录Recovery最后一次status、PID、监听PID、工作目录、SHA、health、数据库/知识/向量manifest。
2. 使用Recovery的`stop_ai_customer_service.ps1`按`Admin → B → A → C API`安全停止；任一记录不可信即停止流程，不做端口强杀。
3. 确认标准端口释放，Recovery数据仍完整；生成最终SQLite/知识/向量一致快照。
4. 将Target配置从影子端口切换为标准端口，API/CORS/UI目标均恢复5173/5174/8000/8011。
5. 使用Target正式启动脚本启动；Target脚本实际依赖顺序为`C API → A → B → C Admin`。
6. 运行完整标准端口验收。通过前不开放客服/运营写入。
7. 全部PASS后由人工确认Target成为当前Runtime；Recovery目录继续保留但不运行。

### Stage E3 — 稳定观察与旧环境保留

- 生成单独的Phase E Execution Report，记录Target四服务身份、数据manifest、测试结果和回滚点。
- 在Phase F另行授权前，不移动、删除、归档Recovery，也不删除Target影子/标准运行证据。
- 只有完成至少一次受管Target停止/重启复核、确认业务数据回滚策略并获得用户批准后，才可讨论旧目录归档。

## 7. 启动顺序

批准顺序：

```text
C API
  ↓ 提供数据库、目录和运营Provider
A
  ↓ 依赖C地址并加载知识/向量、模型
B
  ↓ 依赖A/C
C Admin
  ↓ 依赖C/A
```

因此采用`C API → A → B → C Admin`，与当前正式启动脚本一致。停止顺序反向为`C Admin → B → A → C API`。

每一步必须等前一服务health通过并完成受管listener记录后再继续。A还必须达到`ready=true`、`model_configured=true`、`initialization_error=null`，否则不得启动B。

## 8. 健康与功能保护检查

### 8.1 Runtime身份

四服务均必须记录并验证：

- Repository root为Target绝对路径；
- Git SHA为`26f8cde...`、source state为CLEAN；
- managed PID、listener PID、可执行路径、工作目录、启动时间和端口归属一致；
- A使用Target A venv；C使用Target Python 3.12.13 venv；B/Admin使用Target目录依赖；
- status脚本exit 0，不接受只有HTTP 200但身份不明的进程。

### 8.2 HTTP与代理

| 检查 | 期望 |
| --- | --- |
| C `/health` | HTTP 200，版本与request-id行为正常 |
| A `/api/health` | HTTP 200 |
| A `/api/status` | ready/configured，无初始化错误 |
| B `/` | HTTP 200，页面版本SHA显示Target |
| B `/rag-api/api/health` | 标准端口阶段HTTP 200且来自Target A；影子阶段不得作为Green证据 |
| B `/platform-api/health` | 标准端口阶段HTTP 200且来自Target C；影子阶段不得作为Green证据 |
| Admin `/` | HTTP 200，页面版本SHA显示Target |
| Admin `/ai-api/api/health` | 标准端口阶段HTTP 200且来自Target A；影子阶段不得作为Green证据 |
| Admin `/platform-api/health` | 标准端口阶段HTTP 200且来自Target C；影子阶段不得作为Green证据 |

影子阶段必须通过运行manifest和浏览器网络证据确认B/Admin实际请求目标是18000/18011，不能只看页面可打开，也不能把两个Vite配置中仍固定到8000/8011的代理路径作为Green后端证据。

### 8.3 数据库

- `DATABASE_URL`解析后的绝对路径位于Target，不含Recovery根。
- SQLite只读`PRAGMA integrity_check`为`ok`。
- Alembic为`0008_customer_feedback_loop_v1`。
- 最终静默点Source/Target表行数不变量一致；只记录表名和数量，不输出内容。
- 运行后不得出现意外新数据库文件、自动重建或清空。

### 8.4 A / RAG / 模型

- 知识统计为47 chunks且与迁移manifest一致；不得把历史sync记录替代当前统计。
- Ollama和`qwen3.5:9b`可用。
- 使用冻结TEST目录和一条去标识化合成问题执行人工触发的AI回答smoke。
- 回答非空、含可核对来源、无初始化/模型占位错误；人工核对action、风险和拒答边界。
- smoke不得自动发送给客户，不写反馈、案例、订单或退款，不触发知识同步/发布。

### 8.5 页面与功能保护

B至少验证：

- 客服页面可访问；
- 测试店铺、商品、SKU级联可读取；
- AI回答可生成并保留来源；
- 采用/未采用与反馈入口仍存在，但Phase E切换窗口不提交业务写入；
- 复制前仍需人工确认，不自动发送。

C Admin至少验证：

- 商品知识中心、商品维护、FAQ、安全规则、知识缺口、导入中心、AI问题分析入口可访问；
- 页面读取Target C/A，不展示伪造空数据；
- 不执行上传、审核、状态流转或导入写入。

## 9. 回滚方案

### 9.1 回滚触发条件

出现任一情况立即回滚：

- Target SHA、工作目录、PID/监听记录或解释器身份不匹配；
- 任一标准端口health或固定代理失败；
- Target连接Recovery数据库/向量/资料路径；
- SQLite integrity/revision/行数不变量不一致；
- A未ready、知识统计不一致、AI回答/来源/安全边界失败；
- B或Admin核心页面不可用；
- 发现自动业务动作、意外数据写入或无法证明无人使用；
- 不能安全停止任一受管Target进程。

### 9.2 回滚步骤

1. 保持静默窗口，不允许新的客服/运营写入。
2. 使用Target自己的运行记录和`stop_ai_customer_service.ps1`停止Target；不得按端口杀进程。
3. 验证Target四个标准端口全部释放；保留Target日志、记录和失败数据副本，不删除现场。
4. 确认Recovery仍为`cbc77ed...`、clean，原数据库/知识/向量manifest未变化。
5. 使用Recovery原`config.local.ps1`和Recovery启动脚本恢复`C API → A → B → C Admin`。
6. 使用Recovery状态脚本验证四服务SHA/目录/PID/health，复核47 chunks MATCH、C revision和B/Admin页面。
7. 记录回滚结果；在根因关闭前Target不得再次占用标准端口。

Phase E静默窗口内不允许Target业务写入，因此即时回滚可以回到未变化的Recovery数据。若Target已经在人工开放后产生写入，则不得直接回滚数据库：先停写并备份Target，单独完成数据协调后再决定恢复路径。

## 10. 执行验收Gate

| Gate | 条件 | 失败处理 |
| --- | --- | --- |
| E-G01 Identity | Recovery/Target SHA、clean、contracts正确 | 不启动 |
| E-G02 Quiet Window | 无客服会话与运营写入；用户授权 | 不停止Recovery |
| E-G03 Snapshot | SQLite、知识、向量manifest完整且隔离 | 不启动Green |
| E-G04 Shadow Runtime | 四个影子服务身份和health通过 | 停影子，Recovery继续 |
| E-G05 Shadow Function | 数据库、AI、B/C页面保护通过 | 停影子，Recovery继续 |
| E-G06 Managed Blue Stop | Recovery四个受管服务安全停止 | 不强杀；终止切换 |
| E-G07 Final Handover | 最终静默快照和Target路径验证通过 | 恢复Recovery |
| E-G08 Target Standard | Target四服务标准端口身份/health通过 | 回滚Recovery |
| E-G09 Acceptance | 数据、AI、页面、安全边界全PASS | 回滚Recovery |
| E-G10 Evidence | 执行报告、回滚点、数据manifest齐全 | 不宣布迁移完成 |

只有E-G01至E-G10全部PASS，才可输出`RUNTIME_MIGRATION_COMPLETE`。本计划本身只达到`RUNTIME_MIGRATION_PLAN_READY`。

## 11. 当前只读预检查结果

| 检查 | 结果 |
| --- | --- |
| Recovery身份 | PASS：`cbc77ed...`、clean、四服务均由正式记录验证 |
| Recovery HTTP | PASS：5173/5174/8000/8011均HTTP 200 |
| Recovery数据 | PASS：C revision 0008；A 47 chunks MATCH；未修改 |
| Target身份 | PASS：`26f8cde...`、Tree `9940eb2...`、clean |
| Target依赖 | PASS：四套依赖存在；C Python 3.12.13 |
| Target runtime | PASS：`.runtime`不存在，尚未运行 |
| Git忽略 | PASS：`.runtime`、venv、node_modules、DB、知识、向量、日志均有忽略规则 |
| 影子端口 | PASS（瞬时证据）：15173/15174/18000/18011当前无监听，执行时重检 |
| 启停脚本 | PASS：支持显式RepositoryRoot、RuntimeDirectory、端口和ConfigPath |
| Admin影子路由 | CONDITIONAL：必须显式注入影子A/C地址，禁止沿用默认8000/8011代理 |
| 数据快照 | NOT EXECUTED：只在另行授权的Phase E执行阶段创建 |
| Pilot静默窗口 | NOT SCHEDULED：停止Recovery前必须由用户确认 |

预检查没有发现需要修改冻结代码的阻塞。Admin影子路由和数据快照已经转化为明确的执行Gate，不能靠默认配置或口头确认跳过。

## 12. 禁止事项

Phase E计划与未来执行均不得借机进行：

- R006 Business Data Activation、Legacy状态、activation receipt或任何接口实现；
- UI调整、页面优化、字段新增或业务逻辑变化；
- contracts、requirements、lockfile、Source Tag或Git历史修改；
- 数据库重构、迁移版本新增、重建、清空或测试数据批量改写；
- Master Data、ERP、PostgreSQL、RBAC、Answer Trace；
- A模型、Prompt、RAG算法、知识内容或向量重建；
- 自动发送、自动退款、订单/售后执行；
- 按端口强杀进程、停止Ollama、删除Recovery或处理旧Worktree；
- 把HTTP 200、Phase D PASS或影子页面可打开单独解释为运行迁移成功。

## 13. 下一入口

下一入口只能是用户另行明确授权的：

```text
R008 Phase E Runtime Migration Execution
```

执行授权必须同时给出受控静默窗口。执行从E-G01开始，先建Target忽略运行配置与独立快照，再启动影子环境；不得直接停止Recovery或直接占用标准端口。

最终状态：`RUNTIME_MIGRATION_PLAN_READY`
