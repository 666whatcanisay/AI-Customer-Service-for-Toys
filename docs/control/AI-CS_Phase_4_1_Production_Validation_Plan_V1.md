# AI-CS Phase 4.1 Production Validation Plan V1

> 中文名称：《AI-CS Phase 4.1 生产业务闭环验证计划 V1》
> 计划所有者：AI-CS Control / System Architect
> 验收优先级：P0 — R003；P0 — R005
> 计划基线日期：2026-08-03
> 本轮性质：只生成计划；不执行业务写入，不修改代码、数据库结构、R006/R009核心逻辑
> 计划状态：`AI_CS_PHASE_4_1_PLAN_READY`

## 技术摘要

Phase 4.1 应按“R003 先关闭商品上线链路，R005 再复用同一商品验证真实反馈改善”的顺序串行执行。当前四服务、SQLite、Customer Catalog、Chroma 和 Ollama 均健康，工程能力足以开始准备；但正式执行前仍有一个版本 Gate：仓库内存在尚未提交的交接文档，状态脚本因此将四服务判定为 `DIRTY / 运行身份不一致`。在源码恢复 clean 且 Runtime 身份重新一致前，只允许准备数据和验收脚本，不允许签署生产验收结果。

R003 必须证明一条真实 PILOT 数据从 C 运营准入进入 B，并能由 A 使用；R005 必须使用真实、去标识化的客服问题，形成“未采用事件→AI问题→知识任务→人工补充→增量发布→同题复验”的完整证据链。Mock、直接改库、API 伪造成功、预先编造 badcase 或仅看页面文案都不能构成通过。

## 1. 当前状态确认

### 1.1 Git 与 Runtime

| 项目 | 当前真实状态 | Phase 4.1 判断 |
| --- | --- | --- |
| Repository | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS` | 唯一正式项目目录 |
| Branch | `release/product-reliability-hardening-v1` | 当前正式运行分支 |
| HEAD | `bb16b602ac50a6e554f4e3c42fb10692fff4923f` | 四服务记录的运行 SHA |
| Working tree | `?? docs/control/AI-CS_Project_Handover_Report_V1.md` | 非 clean；执行 Gate 未满足 |
| B | 5173，RUNNING，health 可用 | 可用于后续浏览器验收 |
| Admin | 5174，RUNNING，health 可用 | 可用于运营人工步骤 |
| A | 8000，RUNNING，`ready=true` | 可用于 RAG 问答与发布验证 |
| C API | 8011，RUNNING，health 可用 | 可用于权威状态和收据核对 |
| Runtime mode | `standard / LAN` | A/C/Admin 仅 loopback；B 暴露 5173 |

当前服务可用，但状态脚本显示四服务源码指纹不一致，原因是正式仓库新增了未跟踪治理文档，而运行记录仍对应启动时的 clean tree。正式验收前必须完成以下二选一的受控处理：

1. 将交接包和本计划作为 docs-only 变更纳入批准的 Git 提交，再在静默窗口按标准脚本重启并确认四服务同一新 SHA；或
2. 在不丢失文档的前提下，从与运行 SHA 完全一致的 clean 验收工作区执行，并保存文档到受控治理位置。

不得通过关闭 Runtime 身份检查、忽略 DIRTY 或手改运行记录绕过该 Gate。

### 1.2 数据库、Catalog 与 AI

| 项目 | 当前真实状态 |
| --- | --- |
| 数据库 | `.runtime/phase-e/data/standard-platform.sqlite3` |
| Revision | `0012_internal_production_finalization_v1` |
| 数据质量 | 36 张业务表；integrity、foreign key、孤儿、状态和收据检查全部通过 |
| Store | `INITIAL_IMPORT+ENABLED=1`；`PILOT+ENABLED=1` |
| Product | `INITIAL_IMPORT/TEST_CONFIRMED/ENABLED=5`；`PILOT/APPROVED/ENABLED=2`；`PILOT/APPROVED/DISABLED=17` |
| R003候选 | 17 个 APPROVED+DISABLED PILOT Product；其中 1 个已经 PUBLISHED |
| Customer Catalog | Store envelope=`COMPLETE`，total=2，warnings=0 |
| AI publication | 3 个 Product 为 PUBLISHED，共 9 个商品级 chunks/embeddings |
| A RAG | active collection=`test_knowledge_v031`，56 chunks |
| 模型 | Ollama `qwen3.5:9b`，ready |

### 1.3 R005 当前缺口

| 记录 | 当前数量 | 判断 |
| --- | ---: | --- |
| `ai_interaction_events` | 1 | 仅证明曾保存交互，不构成反馈改善闭环 |
| `ai_problems` | 0 | 尚无真实问题聚合 |
| `ai_problem_occurrences` | 0 | 尚无问题发生链 |
| `knowledge_optimization_tasks` | 0 | 尚无知识优化任务 |
| `ai_response_feedback` | 0 | 尚无真实 AI 回答反馈记录 |

因此 R005 不能沿用历史自动化结果直接关闭，必须产生一条新的、真实且去标识化的完整闭环证据。

## 2. R003 完整业务验收流程

### 2.1 验收目标

证明 C 是 Store/Product 客服可用状态的唯一 Owner，B 只消费 C Customer Available Catalog，A 只根据已提供的商品上下文回答。验收链必须覆盖：

```text
C创建或接收真实PILOT业务数据
  ↓
商品知识人工审核
  ↓
AI知识人工增量发布
  ↓
Store/Product人工启用
  ↓
B目录自动感知
  ↓
A按同一Product/SKU检索并回答
  ↓
停用回滚验证
```

### 2.2 前置 Gate — R003-P0

以下条件缺一不可：

- Git clean，四服务 `repositoryRoot/gitSha/sourceFingerprint/runtimeMode/networkMode` 全部一致。
- 标准 `status_ai_customer_service.ps1` 退出码 0。
- 数据库在线备份、离线回滚快照、SHA-256、`integrity_check=ok` 已记录。
- Chroma、knowledge base 与 publication manifest 已备份；禁止全量重建。
- 运营指定一组真实、获准上线的 PILOT Store/Product/SKU，不包含客户隐私。
- 明确最终期望：验收后保持 ENABLED，还是回到 DISABLED。
- 建立验收编号，例如 `P41-R003-YYYYMMDD-01`，所有截图、receipt 和响应都引用同一编号。

### 2.3 场景 A — Store 准入

| 步骤 | 人工操作 | 系统核对 | 期望结果 |
| --- | --- | --- | --- |
| A1 | 运营在 C Admin 选择一个新建真实 PILOT Store，或在验收窗口中新建获准 Store | C Store详情与数据库只读投影 | 新建 Store 初始 `PILOT+DISABLED` |
| A2 | 不启用 Store，客服打开/聚焦 B | `GET /customer-service/catalog/stores` | Store 不进入 B；其他有效 Store 不受影响 |
| A3 | 运营填写真实 operator 和原因，人工启用 Store | activation API 与 receipt | 状态变为 ENABLED；生成唯一 activation receipt |
| A4 | 保持 B 页面打开，再次聚焦或等待低频刷新 | B Network 与页面 | 无需刷新浏览器，Store 最终出现；刷新不超过 60 秒 |
| A5 | 人工关闭 Store | C 状态、receipt、B 页面 | Store及下游Product从B隐藏；Product自身状态不被改写 |
| A6 | 按最终业务意图重新启用或保持关闭 | C/B | 最终状态与运营签字一致 |

如果本期没有新的真实 Store 可用于 A1，不得创建虚假生产 Store。此时场景 A 只能记为 `CONDITIONAL_PASS`，R003 不能关闭。

### 2.4 场景 B — Product、知识和客服使用

优先选择一个尚未正式上线的真实 PILOT Product。现有数据库有 17 个 `APPROVED+DISABLED` 候选；也可以通过既有 C/R009 流程接收一个获准的新 Product，但不得直接写数据库。

| 步骤 | 人工操作 | 系统核对 | 期望结果 |
| --- | --- | --- | --- |
| B1 | 运营在 C 查看或导入真实 Product/SKU | R009 preflight、Merge、review receipt | 新/变更数据经人工审核；审核前正式 Product 零写入 |
| B2 | 审核通过后查看三态 | 知识、客服、AI状态 | `APPROVED + DISABLED + NOT_GENERATED/NEED_RESYNC/PUBLISHED` 语义明确 |
| B3 | 在 Product 仍 DISABLED 时打开 B | Catalog products envelope | 该Product不可见；其他Product正常，不出现全量 No data |
| B4 | 若AI知识未发布，运营人工点击发布 | publication API、receipt、fingerprint、chunks | `PUBLISHED`；chunks>0；receipt存在；active collection不变 |
| B5 | 运营人工启用 Product | activation API与receipt | Product为ENABLED；Store仍须ENABLED；生成receipt |
| B6 | B保持打开，聚焦或等待低频刷新 | B Network/页面 | Product在60秒内出现；无需手动刷新浏览器 |
| B7 | 客服选择Store→Product→SKU并提问一个有批准事实的问题 | A请求context、回答、citations | A只引用该Product/SKU；答案与批准知识一致 |
| B8 | 检查安全边界 | 页面与响应 | `SUGGESTION_ONLY`；不自动发送、退款或修改订单 |
| B9 | 关闭单个Product | receipt、B目录 | 只隐藏该Product，其他Product继续可用；知识和publication保留 |
| B10 | 重新启用Product并按运营意图确定最终状态 | C/B/A | 可逆且不重复创建；最终状态有审计签字 |

### 2.5 R003 专项异常场景

- 单条异常 Store/Product/SKU 不得清空全部目录。
- `COMPLETE+total=0` 才表示真实空目录。
- `PARTIAL+total=0` 必须显示“商品目录暂时异常，请联系运营处理”，不得显示“没有商品”。
- `PARTIAL+items>0` 显示有效 items，并提示部分异常。
- Store DISABLED 阻断下游投影，但不修改 Product 的 `customer_service_status`。
- Product DISABLED 不删除知识、chunks、embedding、import history 或 receipt。
- activation idempotency 重试不得重复产生业务状态变化。

## 3. R005 Feedback 真实闭环验收流程

### 3.1 验收目标

使用真实客服工作中的一条去标识化问题，证明 B 的人工判断可以进入 C 的问题与知识优化链，知识变化经人工审核和增量发布后，A 对同一问题产生可核对的改善结果。

R005 不验证“模型一定会变聪明”；它验证的是可追溯闭环。如果补充知识后仍未改善，必须记录 `NOT_IMPROVED` 并保持任务开放，不能伪造 PASS。

### 3.2 真实样本准入

样本必须同时满足：

- 来源于真实客服工作或真实运营已知问题，不为验收临时编造。
- 已去除姓名、电话、地址、订单号、聊天截图和其他客户隐私。
- 绑定 R003 已通过的 Store/Product/SKU。
- 有明确、经运营批准的事实答案和来源材料。
- 当前 AI 回答确实存在缺失、错误或无法回答，客服可合理选择“未采用”。

若验收窗口内没有真实 badcase，R005 保持 `TODO/BLOCKED_BY_SAMPLE`，不得人为制造错误反馈。

### 3.3 闭环步骤

| 步骤 | 人工操作 | 系统证据 | 通过条件 |
| --- | --- | --- | --- |
| F1 基线提问 | 客服在 B 选择同一Store/Product/SKU，输入真实去标识化问题 | question、context、answer、citations、时间、当前fingerprint/receipt | 保存“改善前”基线，不编辑问题语义 |
| F2 人工判定 | 客服判断回答不可用，选择“未采用”，选择真实原因并填写去标识化说明 | B页面、C interaction receipt | C返回真实receipt；B不伪造本地成功 |
| F3 问题进入C | 运营进入AI问题中心 | event ID、problem ID、occurrence | 新问题形成或聚合到正确问题；Store/Product/SKU一致 |
| F4 人工确认 | 运营检查问题事实，变更问题状态并创建知识优化任务 | problem status receipt、task ID | 所有状态变化有operator和时间 |
| F5 补充知识 | 运营通过既有知识维护/资料审核流程补充缺失事实 | old/new值、review receipt、approved source | 不直接改库；知识必须人工审核 |
| F6 检测变化 | 运营查看AI知识状态 | old/new fingerprint、status | 内容变化触发 `NEED_RESYNC` 或等价可见状态 |
| F7 增量发布 | 运营人工发布AI知识 | publication receipt、collection、chunks、embeddings | 新fingerprint发布成功；不全量重建；其他Product知识不丢失 |
| F8 同题复验 | 客服使用相同Store/Product/SKU和同义不变的问题重新提问 | after answer、citations、新receipt/fingerprint | 新答案引用新知识，事实完整度提高，无跨商品污染 |
| F9 人工评价 | 原客服或独立QA按事实清单评价 | `IMPROVED/NOT_IMPROVED`、说明、verified_by/at | 结果如实记录；未改善不得关闭任务 |
| F10 闭环签字 | 运营、客服、QA联合签字 | 全链ID映射表 | event→problem→task→review→publication→retest 可追溯 |

### 3.4 改善的判定方法

“改善”不按文案相似度判断，按同一事实清单比较：

| 指标 | 改善前 | 改善后通过条件 |
| --- | --- | --- |
| 上下文绑定 | 记录 Store/Product/SKU | 必须完全相同 |
| 核心事实覆盖 | 由运营列出必答事实 | 缺失事实被正确补齐 |
| 错误事实 | 逐项记录 | 不新增错误，不保留已修正错误 |
| 引用 | 记录来源数量和Product归属 | 至少1条有效来源，且来自同Product/SKU |
| 安全边界 | 记录action与提示 | 继续人工确认；无自动业务承诺 |
| 客服可用性 | 未采用 | 由客服判为可采用或修改后可采用，并说明理由 |

建议在发布后连续复验两次，以排除单次生成波动；两次都必须满足核心事实和来源边界。该重复仅用于稳健性核对，不修改 Prompt 或模型参数。

## 4. 需要准备的数据

### 4.1 R003 数据包

| 数据 | 必填内容 | 责任人 |
| --- | --- | --- |
| Store | 真实业务名称、平台、业务状态、最终是否上线 | 运营Owner |
| Product | 真实商品名称、Store归属、审核状态、客服初始状态 | 运营Owner |
| SKU | SKU名称/规格、父Product、至少一个可核对差异 | 运营Owner |
| 商品知识 | 年龄、材质、玩法/卖点、安全限制等批准事实 | 知识审核人 |
| 来源 | 已批准文件或系统来源ID；不得含客户隐私 | 知识审核人 |
| 操作人 | 启用、审核、发布所用的稳定operator标识 | Control |
| 最终状态 | 验收结束后Store/Product保持ENABLED或回到DISABLED | 业务Owner |

优先使用一件计划真实上线的 PILOT 商品。不得重复导入同一 Product 制造“新商品”，也不得为通过验收改动现有产品事实。

### 4.2 R005 数据包

| 数据 | 必填内容 | 责任人 |
| --- | --- | --- |
| 真实问题 | 去标识化客服问题原意 | 客服代表 |
| 改善前回答 | 原始A回答、action、citations | QA |
| 预期事实清单 | 必答事实、禁止推断、安全边界 | 运营+QA |
| 缺失知识 | 需要补充的最小事实，不扩展其他业务 | 运营 |
| 审核来源 | 能证明新事实的批准资料 | 知识审核人 |
| 链路ID | interaction/problem/occurrence/task/review/publication receipt | Control |
| 改善后回答 | 两次复验回答和引用 | QA |
| 最终评价 | IMPROVED或NOT_IMPROVED及理由 | 客服+QA |

### 4.3 保护与证据包

- 执行前 Git/Runtime 身份快照。
- SQLite 在线备份、离线回滚快照、SHA-256、integrity manifest。
- Chroma collection 列表、active collection、总 chunks、商品级 chunks/fingerprint。
- 执行前后 Customer Catalog envelope。
- 浏览器截图、Network 请求与返回；所有客户信息先脱敏。
- activation、review、publication、interaction 和 verification receipt。
- 执行后数据库健康检查报告。

证据放入 Git 忽略的 `.runtime/phase-4-1/evidence/<validation-id>/`，正式报告只记录脱敏摘要和受控ID，不提交数据库、向量、原始客户内容或浏览器个人数据。

## 5. 需要人工参与的步骤

| 角色 | 不可自动代替的决定 |
| --- | --- |
| Control / 架构负责人 | 确认clean基线、范围、静默窗口、Gate与最终签字 |
| 数据保护负责人 | 执行并验证数据库/RAG备份；决定是否回滚 |
| 运营Owner | 指定真实Store/Product/SKU；审核知识；决定启用、停用和最终状态 |
| 知识审核人 | 判断新知识是否真实、充分、可发布 |
| 客服代表 | 提出真实问题；判断采用、修改后采用或未采用；评价改善结果 |
| QA | 保持前后问题和上下文一致；核对页面、API、receipt和引用 |
| 网络/OPS | 保持标准Runtime；只有R007单独安排时才负责第二终端网络 |

必须人工确认的按钮/动作包括：知识审核通过、AI知识发布、Store启用/停用、Product启用/停用、AI回答采用判定、AI问题确认、知识任务复验和最终业务签字。

Playwright 可以辅助记录页面和等待状态，但不得替代上述业务判断，也不得直接调用API或写数据库模拟人工步骤。

## 6. 验收标准

### 6.1 R003 PASS 标准

以下全部满足才可把 R003 从 `IN_PROGRESS` 改为 `DONE`：

1. 至少一组获准 PILOT Store/Product/SKU 通过真实 C 运营流程进入系统。
2. 新数据在人工启用前不进入 B；默认状态证据完整。
3. Store和Product实际状态变化均生成可查询的activation receipt。
4. B只消费Customer Catalog，60秒内自动感知启用/停用，不需要刷新浏览器。
5. 单条异常不影响其他目录；四种 envelope 语义保持正确。
6. Store停用阻断下游，但不改Product状态；Product停用不删除知识和发布记录。
7. A在正确Product/SKU上下文内回答，引用对应商品知识，无跨商品污染。
8. 全程保持人工确认、不自动发送、不退款、不改订单。
9. 执行后数据库健康检查P0/P1=0，RAG无非目标数据丢失。
10. 运营、客服、QA共同签字，最终状态符合业务Owner决定。

如果缺少真实新Store创建证据，只能记为 `R003_CONDITIONAL_PASS`，不能关闭R003。

### 6.2 R005 PASS 标准

以下全部满足才可把 R005 从 `TODO` 改为 `DONE`：

1. 使用至少一条真实、去标识化、可核对的客服badcase。
2. B提交后获得C真实interaction receipt，不存在本地伪成功。
3. event、problem、occurrence、knowledge task完整关联到同一Store/Product/SKU。
4. 知识变更经过人工审核，正式知识在审核前不被修改。
5. 内容fingerprint发生预期变化，商品进入需重同步状态。
6. 增量发布产生新的publication receipt，chunks/embeddings>0，未全量重建RAG。
7. 同一问题、同一上下文复验两次；核心事实正确、同商品引用、安全边界通过。
8. 客服与QA共同判断 `IMPROVED`，并在知识任务中记录验证结果。
9. 执行后数据库健康、Catalog和四服务继续正常。
10. 整条链路具有脱敏截图、请求回执和ID映射，可由第三方复核。

如果结果为 `NOT_IMPROVED`，说明工程闭环可用但业务改善未达成：知识任务保持开放，R005不关闭，也不得在本阶段通过修改Prompt、模型或RAG架构强行通过。

### 6.3 Phase 4.1 总 Gate

```text
P4_1_PREFLIGHT_PASS
  ↓
R003_PRODUCTION_VALIDATED
  ↓
R005_REAL_FEEDBACK_LOOP_VALIDATED
  ↓
AI_CS_PHASE_4_1_VALIDATION_COMPLETE
```

任一 P0 Gate 失败，整体状态必须为 `AI_CS_PHASE_4_1_VALIDATION_BLOCKED`，并记录明确断点；不得以部分页面成功替代完整闭环。

## 7. 风险与控制措施

| 等级 | 风险 | 控制措施 |
| --- | --- | --- |
| P0 | 当前源码DIRTY导致Runtime身份不一致 | 先建立clean、可追溯的docs-only基线并按受控窗口对齐Runtime，禁止绕过身份检查 |
| P0 | 在正式数据库执行真实业务写入 | 执行前双备份和hash；只通过现有UI/API；禁止SQL直写、migration和清库 |
| P0 | 无真实badcase却强行关闭R005 | 样本由客服提供并签字；没有样本则保持待处理 |
| P1 | 误启用错误Store/Product | 操作前双人核对业务名称/ID；使用人工确认；预先定义最终状态和停用回滚 |
| P1 | RAG发布影响非目标商品 | 记录发布前后active collection与商品级fingerprint/chunks；只允许增量发布 |
| P1 | 模型生成随机性导致误判改善 | 固定上下文和事实清单；发布后复验两次；按事实和引用判定，不按措辞 |
| P1 | 客户隐私进入反馈或证据 | 输入前脱敏；禁止姓名、电话、地址、订单号和原始聊天截图进入Git |
| P1 | R003与R005使用不同商品导致链路不可比 | R005优先复用R003已通过的同一Product/SKU |
| P1 | Catalog PARTIAL被误判为空 | 保留status/total/warnings/items；执行四态回归，不只看items |
| P2 | B自动刷新有最多60秒延迟 | 同时验证focus刷新和低频刷新；不引入WebSocket/SSE |
| P2 | 第二终端网络阻塞干扰业务验收 | Phase 4.1先用服务器本机/受控浏览器；R007另行验收，不改业务代码 |
| P2 | 历史物理名称含`test_*` | 只核对业务状态和投影，不重命名表/collection、不重建RAG |

## 执行顺序与交付物

计划批准后，建议拆成三个受控执行包：

1. `Phase 4.1-0 Preflight Report`：clean Runtime、备份和候选数据确认。
2. `R003 Production Business Acceptance Report V1`：Store/Product/SKU准入、目录、A回答及回滚。
3. `R005 Real Feedback Loop Acceptance Report V1`：改善前后、收据链、人工评价与最终Gate。

本计划不授权新增架构、数据库结构、模板、Prompt、模型或自动化业务动作。任何超出既有R006/R006.1/R006.2/R009流程的需求必须重新登记并单独冻结。

---

最终状态：`AI_CS_PHASE_4_1_PLAN_READY`
