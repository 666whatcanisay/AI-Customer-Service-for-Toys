# AI-CS Monorepo Source Freeze Report V1

> 需求：R008 — AI-CS Project Structure Simplification V1
>
> 阶段：Phase 1 — Monorepo Source Freeze
>
> 冻结日期：2026-07-30
>
> 迁移源：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-r006-interface-validation-v1`
>
> 分支 / HEAD：`control/r006-interface-validation-v1-1@19cc82682074dc0f11096d4191ad8d19a9f0cc0b`
>
> 当前实际Pilot运行锚点：`control/pilot-baseline-recovery-v1@cbc77ed883cb99e2eff76ccb8eb3193bbddaba38`
>
> 当前contracts：`0.2.0`
>
> 执行方式：只读Git、目录树、功能路径、数据边界、端口、PID记录与health核验
>
> Gate：`CONDITIONAL PASS / MONOREPO_SOURCE_FREEZE_READY / PHYSICAL_MIGRATION_BLOCKED`

## 0. 冻结结论

本轮已经建立可复核的迁移前双锚点：

1. **迁移内容锚点**：`19cc826...`。`backend`、`frontend`、`extension`、`platform_backend`、`admin_web`、`contracts`、`scripts`和`tests`均有固定Git tree object，可在未来目录迁移后逐项比对。
2. **Pilot运行/回滚锚点**：`cbc77ed...`。5173、5174、8000、8011当前全部由clean `AI-CS-pilot-baseline-recovery-v1`运行，监听PID与受管记录匹配，四项只读health均返回HTTP 200。

`cbc77ed...`是`19cc826...`的祖先；两个提交之间上述八个代码/契约/脚本/测试目录的tree object完全相同，只有`docs/control/**`发生提交差异。因此迁移源包含当前已验证Pilot的同一业务代码，并额外包含R006接口治理文档。

迁移源工作树不是clean。Phase 1开始时有7个R008 Control文档变更，没有A/B/C、contracts、scripts或tests修改。本报告和同步文档完成后，Control文档覆盖层将继续保持未提交，因为本阶段禁止修改Git历史。该状态已经被显式登记，不能在Phase 2中被覆盖、忽略或用`git add .`混入目录迁移。

本轮没有创建`AI-CS/`，没有移动文件，没有删除Worktree，没有修改代码、UI、contracts、数据库或业务数据，没有停止/重启服务，也没有commit、push、branch、Tag、merge、rebase或历史改写。

## 1. 迁移源确认

### 1.1 Git身份

| 字段 | 冻结值 | 判断 |
| --- | --- | --- |
| repository root | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-r006-interface-validation-v1` | 与用户指定迁移源一致 |
| branch | `control/r006-interface-validation-v1-1` | 一致 |
| HEAD | `19cc82682074dc0f11096d4191ad8d19a9f0cc0b` | 一致；本轮未改变 |
| contracts | `contracts/version.json = 0.2.0` | 一致；本轮未修改 |
| Pilot Tag | `ai-cs-pilot-baseline-v1`解引用到`cbc77ed883cb99e2eff76ccb8eb3193bbddaba38` | 现有正式回滚点 |
| ancestry | `cbc77ed...`是`19cc826...`祖先 | PASS |
| Phase 1开始时clean | `false` | 7个Control文档覆盖层；实现目录为0项变更 |
| 新保护Tag | 未创建 | 本阶段禁止修改Git历史；进入物理迁移前必须另获授权 |

### 1.2 dirty覆盖层冻结

Phase 1开始时以下文件位于`19cc826...`之上。SHA-256只用于识别本次规划覆盖层，不把它们解释为已提交版本：

| 状态 | 文件 | Phase 1开始时SHA-256 |
| --- | --- | --- |
| M | `docs/control/01_三线状态看板.md` | `d5235349ec01f4c92e4ded9b30cab499ca045eb165f0ace912e20458500baad4` |
| M | `docs/control/10_变更记录.md` | `ae07f8652e92f1dd092faab18adcda71ebafb345615f9d999d471cf33d0e5dd4` |
| M | `docs/control/11_交接说明.md` | `c4ca464652baafb6b523329fd9fc38a8c712f35c5df9bb57091500777f908fd0` |
| M | `docs/control/AI-CS-Current-Requirement-Status-Summary.md` | `71bcdd0733b37b51832dc9cc5ede584450f17840428639ef5eed6e3aaaa85dc0` |
| M | `docs/control/AI-CS-Requirement-Registry-V1.md` | `6e262790729e6f92e48affbbf939f4908c436a561d71c2b68ffa952f78d76efd` |
| M | `docs/control/machine-context.json` | `a04b572132c7cd791f74684f36aff235b3582562a7e471d17a7bdcbf086b8a6e` |
| ?? | `docs/control/AI-CS-Monorepo-Migration-Plan-V1.md` | `d42071239435e8367ffb3b2a9cd7b72a4037cc146c408c322611a69365800c3a` |

实施边界：上述覆盖层必须在下一阶段前得到明确的“提交到受控文档commit”或“外部归档后恢复clean”决定。本报告不授权其中任何一种，也不授权丢弃。

### 1.3 与当前Pilot基线的目录一致性

| 目录 | `cbc77ed...` tree | `19cc826...` tree | 结果 |
| --- | --- | --- | --- |
| `backend` | `46f1f4aa0ee755393bf78ce1ee92dad9a8c7875e` | 相同 | IDENTICAL |
| `frontend` | `4d799481555c34407f9f05c3ac05a3b54eb356c5` | 相同 | IDENTICAL |
| `extension` | `a59d7037e4b998c9555f279c89e1a27944fc385f` | 相同 | IDENTICAL |
| `platform_backend` | `236ab010ec6d93fe389c0408b5698cdebd4c6b19` | 相同 | IDENTICAL |
| `admin_web` | `b16494deab348a689164acb348d4d974737cd748` | 相同 | IDENTICAL |
| `contracts` | `0d5ed3f5d06cc9a6c36a8973c1f9d25c41764640` | 相同 | IDENTICAL |
| `scripts` | `d28a084515aa638fcd731d75a944dc5b866ad7d9` | 相同 | IDENTICAL |
| `tests` | `333267b947df8e3e6332709a6c5242f3841197d5` | 相同 | IDENTICAL |
| `docs` | `61432e47840363b3bd24398dc192ebb872ac0f67` | `d0c7745e9f10590f1347a73533d9ae6c8e64c6e8` | EXPECTED DIFFERENCE：仅Control治理文档 |

## 2. 目录迁移冻结表

以下是未来迁移允许使用的唯一源→目标映射。本轮没有执行这些动作。

| 当前目录 | HEAD tree / tracked文件数 | 目标目录 | 冻结规则 |
| --- | --- | --- | --- |
| `backend/` | `46f1f4aa...` / 40 | `AI-CS/apps/ai-service/` | 只做路径迁移；不得修改A接口、RAG、模型或Prompt |
| `frontend/` | `4d799481...` / 79 | `AI-CS/apps/customer-client/` | 保留5173、客服流程、AI回答和反馈；不得重做UI |
| `extension/` | `a59d7037...` / 1 | `AI-CS/apps/customer-client/extension/`或经B Owner确认后进入archive | 未确认前不得删除 |
| `platform_backend/` | `236ab010...` / 97 | `AI-CS/services/platform-api/` | 保留8011、Alembic、C Provider与全部业务数据语义 |
| `admin_web/` | `b16494de...` / 74 | `AI-CS/apps/admin-console/` | 保留5174和现有运营页面；不得优化页面 |
| `contracts/` | `0d5ed3f5...` / 13 | `AI-CS/contracts/` | 原结构保留，版本固定0.2.0 |
| `docs/` | `d0c7745e...` / 155 committed + R008覆盖层 | `AI-CS/docs/` | R001–R008与接口/Recovery证据不得丢失；覆盖层先单独收敛 |
| `scripts/` | `d28a0845...` / 56 | `AI-CS/scripts/` | 未来只允许相对路径适配；本轮不修改、不运行停止/启动动作 |
| `tests/` | `333267b9...` / 2 | `AI-CS/tests/` | 根集成骨架保留；模块测试继续随各应用迁移 |

任何未来迁移都必须通过`source tree → target tree`清单核验。纯`git mv`后内容对象应保持不变；若因路径适配导致tree变化，必须逐文件说明原因并通过对应模块回归，不能用一个总diff掩盖行为变化。

## 3. 功能保护清单

### 3.1 B — 客服工作台

| 必保能力 | 冻结入口 | 迁移后最低验收 |
| --- | --- | --- |
| 客服页面与选品咨询流程 | `frontend/src/views/AiChat.vue`、`WorkspaceHome.vue`、平台目录client/adapter | 5173页面可用；店铺/商品/SKU级联、问题输入、人工处理路径和错误状态不变 |
| AI回答 | `frontend/src/api/ragClient.ts`、`ragAdapter.ts`、`ragTypes.ts` | 继续通过既有A接口生成建议；来源、安全提示、人工确认、复制边界不变；禁止自动发送 |
| 采用行为与反馈沉淀 | `aiInteractionEvent*`、`aiResponseFeedback*`、`experienceCase*` | 采用/修改后采用/未采用均只在C真实回执后成功；幂等和失败语义不变 |
| B回归资产 | `frontend/src/**/*.spec.ts`及构建配置 | typecheck、全量Vitest、production build通过 |

禁止把“页面能打开”替代AI回答和反馈链路验收，也不得借目录迁移重新设计客服UI或R006 Consumer。

### 3.2 C — 运营中心与Platform API

| 必保能力 | 冻结入口 | 迁移后最低验收 |
| --- | --- | --- |
| 商品知识中心 | `platform_backend/app/product_knowledge/`、`knowledge_materials/`、`KnowledgeCenterView.vue`、`KnowledgeEditorView.vue` | 店铺→商品→SKU知识、模板、状态与来源可用 |
| 商品维护 | `platform_backend/app/operation_management/`、`StoreManagementView.vue`、`ProductDetailView.vue` | 店铺/商品创建与维护行为不变；不实施R006激活字段 |
| FAQ | `test_catalog/`、`knowledge_materials/`、`ReadonlyListView.vue`、`KnowledgeEditorView.vue` | FAQ查看、受控维护、来源与适用范围不丢失 |
| 安全规则 | `test_catalog/`、`KnowledgeEditorView.vue`、Admin安全规则路由 | 风险、禁止承诺、人工确认和转人工条件不丢失 |
| 知识缺口 | `product_knowledge/`、`KnowledgeGapCenterView.vue` | 缺口识别、排序和运营查看不丢失 |
| 导入中心 | `platform_backend/app/ingestion/`、`ImportCenterView.vue`、11份tracked模板 | 商品/SKU/FAQ/安全/知识缺口模板和人工审核边界不丢失；不得自动发布知识 |
| AI问题分析 | `customer_feedback_loop/`、`ai_feedback/`、`AiIssueCenterView.vue`、`AiFeedbackOptimizationPoolView.vue` | C权威保存、问题中心、知识任务和分析证据不丢失 |
| C回归资产 | `platform_backend/tests/`、`admin_web/tests/`、`admin_web/src/App.spec.ts` | C pytest、Alembic往返、Admin typecheck/Vitest/build通过 |

### 3.3 A — AI能力层

| 必保能力 | 冻结入口 | 迁移后最低验收 |
| --- | --- | --- |
| RAG编排 | `backend/app/service/rag_service.py`、`test_knowledge.py` | 既有范围过滤、安全回答、拒答与来源证据不变 |
| 模型调用 | `rag_service.py`、`config/settings.py`、A API routes | 继续使用受控本机模型配置；不得切换模型、修改Prompt或自动训练 |
| 检索与向量读取 | `vector_store.py`、`document_loader.py`、`/api/retrieval/search` | tenant/store/product/SKU范围和安全规则检索不变；不得重建或清空现有向量 |
| A回归资产 | `backend/tests/`的11个`test_*.py` | A全量pytest通过；真实RAG测试仍按显式环境Gate执行 |

### 3.4 共享能力与基线证据

- contracts 0.2.0的7个schema、CHANGELOG、compatibility和error codes全部保留。
- R001 C商品知识运营中心V2不得重新设计。
- R002 Customer Feedback Loop不得退化为前端本地成功。
- R003/R006仍未实现Business Data Activation，迁移不得伪造完成。
- R004 Recovery Tag、六个能力commit、测试与运行报告必须继续可达。
- R005真实Pilot验证仍为TODO。
- R007仍是独立网络Gate。

R004已保存的回归基线为：A `101 passed / 3 skipped`、C Backend `95 passed`、B `28 files / 115 tests`、Admin `25 files / 54 tests`、7个contracts schema校验通过、Alembic head为`0008_customer_feedback_loop_v1`。这些结果是迁移后的最低等价比较基线，不代表本轮重新执行了测试。

## 4. 数据保护规则

### 4.1 强制禁止

整个R008结构迁移期间禁止：

- 删除、覆盖、移动或直接编辑Pilot SQLite数据库。
- 重建数据库、清空表、重新初始化为Demo数据或运行未批准migration。
- 清空知识包、知识资料、FAQ、安全规则、反馈、问题中心、知识任务或运行证据。
- 删除、重建或重新同步现有向量库来“验证路径”。
- 修改Store/Product/SKU或任何`customer_service_status`业务数据。
- 把`.runtime`、数据库、日志、知识源、向量、模型、客户数据、依赖或构建产物复制进Git或`archive/`。

### 4.2 当前受保护运行资产

当前实际运行根`AI-CS-pilot-baseline-recovery-v1`中只读确认：

| 资产 | 当前事实 | 保护要求 |
| --- | --- | --- |
| `.runtime/data/` | 1个SQLite文件，约733,184 bytes | 运行中不直接复制/哈希；未来使用既有SQLite在线备份入口生成可恢复备份 |
| `.runtime/logs/` | 8个运行日志文件 | Git忽略；只用于OPS诊断，不进入迁移提交 |
| `backend/vector_db/` | 5个忽略文件，约1,038,500 bytes | 保持原位；不得删除、重建或提交 |
| `backend/knowledge_base/` | 仅tracked边界README | 不得将真实源知识放入Git |
| `.runtime/*.json` | 四服务受管运行记录与同步记录 | 原位保留，禁止删除或伪造新记录 |

文件数和大小只用于确认资产存在，不代表内容质量或数据库一致性。本轮没有读取客户内容、知识正文、向量内容或数据库记录。

### 4.3 迁移前后数据Gate

未来每次运行切换前必须：

1. 记录数据库路径、文件大小、Alembic revision和在线备份receipt。
2. 对SQLite使用应用批准的online backup，不在服务运行时直接复制数据库文件。
3. 记录知识/向量集合数量的脱敏统计，不导出正文。
4. 迁移后只读核对表/知识/反馈数量与关键状态；禁止通过重新导入补齐差异。
5. 任何数量下降、revision漂移或路径指向空库，立即停止切换并执行第6节回滚。

## 5. 运行保护规则

### 5.1 当前真实运行身份

2026-07-30只读核验结果：

| 端口 | 服务 | 受管PID / 监听PID | 运行目录 | 记录SHA | health |
| ---: | --- | --- | --- | --- | --- |
| 5173 | B客服工作台 | `33360 / 33360` | `AI-CS-pilot-baseline-recovery-v1/frontend` | `cbc77ed...` | `/` HTTP 200 |
| 5174 | C Admin | `30732 / 38224` | `AI-CS-pilot-baseline-recovery-v1/admin_web` | `cbc77ed...` | `/` HTTP 200 |
| 8000 | A能力层 | `20384 / 24844` | `AI-CS-pilot-baseline-recovery-v1/backend` | `cbc77ed...` | `/api/health` HTTP 200 |
| 8011 | C API | `19020 / 44428` | `AI-CS-pilot-baseline-recovery-v1/platform_backend` | `cbc77ed...` | `/health` HTTP 200 |

运行记录根为clean `control/pilot-baseline-recovery-v1@cbc77ed...`、contracts 0.2.0。监听PID、可执行类型、启动时间和记录中的listener PID一致；旧原Control目录的运行记录指向较早且当前不匹配的PID，不能用于停止当前服务。

结论：当前Pilot没有从迁移源`19cc826...`运行。`AI-CS-pilot-baseline-recovery-v1`是正在使用的运行目录，不得在结构迁移、Worktree清理或目录改名中处理。

### 5.2 迁移前后强制验证矩阵

| Gate | 迁移前 | 迁移后 |
| --- | --- | --- |
| Git身份 | repository root、branch/tag、full SHA、clean、contracts | 新`AI-CS/`同样五项；四服务必须同一release SHA |
| 5173 | listener/record/PID、`/` 200、固定A/C代理、客服页面 | 同项；商品选择、AI回答、反馈回执人工验证 |
| 5174 | listener/record/PID、`/` 200 | 同项；商品知识、导入、缺口、AI问题中心可读 |
| 8000 | listener/record/PID、`/api/health` 200 | 同项；受控真实AI smoke、检索范围与来源证据 |
| 8011 | listener/record/PID、`/health` 200 | 同项；目录、知识和Feedback Loop只读/受控写验收 |
| 数据 | 数据库revision、备份receipt、脱敏数量 | revision和数量不降；不得自动重建或重新导入 |
| 安全 | 人工确认、无自动发送/退款/业务动作 | 完全相同 |

不得只凭端口监听或HTTP 200宣称迁移成功。运行记录中的repository root和SHA必须与目标release一致，B的两条固定代理和关键业务路径必须同时验证。

### 5.3 本阶段运行边界

- 不停止、重启或替换当前四服务。
- 不打开防火墙、不改变监听地址、不处理R007。
- 不删除任何受管记录、PID记录、日志或数据。
- 不对未知或过期记录执行按端口强杀。

## 6. 回滚方案

### 6.1 当前回滚锚点

- Git：`ai-cs-pilot-baseline-v1@cbc77ed883cb99e2eff76ccb8eb3193bbddaba38`。
- 物理目录：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-pilot-baseline-recovery-v1`。
- 分支：`control/pilot-baseline-recovery-v1`。
- 状态：clean，contracts 0.2.0，当前四服务正在使用。
- 数据：该目录下被Git忽略的`.runtime`、SQLite、运行记录、日志和向量保持原位。

在新Monorepo完成受控运行切换和回滚演练之前，该目录、分支、Tag、依赖、运行记录和数据都不得删除、移动或重命名。

### 6.2 未来失败处置

#### A. 目录迁移或静态测试阶段失败

1. 停止继续修改迁移分支。
2. 保留失败diff和测试证据；不使用`reset --hard`改写历史。
3. 旧Pilot继续在`cbc77ed...`运行，不做任何服务动作。
4. 修正计划或重新从冻结SHA创建新的受控迁移候选。

#### B. 隔离运行验证失败

1. 只停止有可信运行记录的隔离目标服务。
2. 确认标准端口5173/5174/8000/8011上的旧Pilot未被触碰。
3. 保留隔离数据库和日志用于诊断，但不得提交Git。
4. 回到迁移前Gate，不删除Recovery目录。

#### C. 正式切换后失败

1. 使用新根的可信记录安全停止新服务；禁止按端口强杀。
2. 若结构迁移未改变数据，继续使用原受保护数据路径；若未来另有获批数据变更，只能使用已验证online backup恢复。
3. 从`AI-CS-pilot-baseline-recovery-v1@cbc77ed...`使用正式OPS脚本启动C API → A → B → C Admin。
4. 复核四个listener PID、record root/SHA、四项health、5173固定代理、目录、AI回答和Feedback Loop。
5. 所有Gate恢复后才结束回滚；失败则保持BLOCKED并请求人工处置。

禁止用数据库重建、Alembic盲目降级、知识重导入或向量重建代替回滚。

## 7. Phase 1 Gate与剩余阻塞

| Gate | 结论 | 证据 / 条件 |
| --- | --- | --- |
| 迁移源root/branch/SHA确认 | PASS | 指定源与实际一致，HEAD未变 |
| contracts版本确认 | PASS | 0.2.0，tree与Pilot基线一致 |
| 九个目录树冻结 | PASS | tree object和tracked数量已记录 |
| B/C/A功能保护 | PASS | 所有最小入口存在且tracked；基线测试证据可追溯 |
| 数据删除/重建边界 | PASS | 运行资产只读存在，Git忽略规则有效 |
| 四服务运行身份 | PASS | 当前均来自clean `cbc77ed...`，listener与记录匹配，health 200 |
| 迁移源clean | FAIL / `SF-B01` | 7个起始Control文档覆盖层，本轮后将增加Source Freeze文档与同步修改 |
| 19cc保护Tag | NOT EXECUTED / `SF-B02` | 本阶段禁止修改Git历史；进入物理迁移前需明确授权保护引用 |
| 其他dirty Worktree归属 | OPEN / `SF-B03` | 8个既有dirty Worktree仍隔离，未授权提交、删除或归档 |
| 物理迁移授权 | BLOCKED | 本轮禁止创建`AI-CS/`、移动或删除 |

总体Gate：`CONDITIONAL PASS`。

`MONOREPO_SOURCE_FREEZE_READY`表示迁移源、功能、数据、运行和回滚快照已经形成，不表示允许进入物理迁移。下一入口只能是R008 `Source Clean & Protection Reference Closure`：由用户决定R008文档如何形成受控commit/归档并授权保护引用；同时保持当前Pilot和所有dirty Worktree不变。关闭`SF-B01`和`SF-B02`前，不得创建`AI-CS/`或执行`git mv`。

## 8. 本轮未执行事项

本轮没有创建目标目录，没有移动、复制或删除任何项目文件，没有删除或清理Worktree，没有修改A/B/C代码、UI、contracts、数据库、知识、向量或业务数据，没有停止/重启服务，没有创建/移动/删除branch或Tag，没有commit、push、merge、rebase、reset或修改Git历史。

最终状态：`MONOREPO_SOURCE_FREEZE_READY`
