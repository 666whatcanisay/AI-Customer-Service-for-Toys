# AI-CS PDD 回答优化与商品风险调整池 V1 完成报告

日期：2026-08-14

Gate：`PASS / AI_CS_PDD_REPLY_READINESS_CARD7_READY / SOURCE_ONLY`

UI补充Gate：`PASS / AI_CS_PDD_REPLY_READINESS_CARD7_UI_READY / SOURCE_ONLY`

## 运营UI优化补充

- `/reply-readiness`严格隔离商品级与SKU级问题、资料和运行，使用请求epoch拒绝晚响应；超时只用同一幂等键恢复既有运行并轮询详情。
- 风险结论改为运营中文、默认高风险优先并支持搜索/分类/动作/风险筛选；原始代码、ID和哈希折叠到技术详情，移动端使用问题卡片。
- `/knowledge-editor`完整回填四种模板，修订模式锁定业务范围、模板和资料身份，当前提交人保持空白；增加未保存保护、字段分组、完整度和安全风险即时提醒。
- C Admin列表只增加兼容的可选范围参数，没有新表或迁移；全局Admin导航和顶部环境语义不在本补充范围。
- UI补充验证：C定向`12 passed`；Admin定向`11 passed`、全量`37 files / 102 tests passed`、typecheck和production build通过。

## 完成内容

- 建立 36 类脱敏、版本化 PDD 问题基线，覆盖普通话术、商品事实、商品推荐、发货物流、售后、真假授权、返现和支付等类别。
- 新增 STORE/PRODUCT 问题扩展投影；扩展只能增加问题/别名/必需事实、提高风险或收紧动作，不能删除强制题、降低政策底线或取消实时查询。
- 新增冻结运行账本，绑定商品/SKU、问题集指纹、知识修订、ReplyRule 快照、Router 构建和内存 Replay 身份。
- A 使用真实 `ReplyRouter.decide()` 和独立内存 Provider 评测；统一计算 `effective_risk = max(policy, router, evidence gap)`。
- 保存逐题动作、来源类型、回答预览/哈希、缺失事实、阻断码、禁止声明命中、引用身份和证据包哈希。
- 支持草稿修订复跑和同范围运行比较；失败运行不展示或复用旧结果。
- 知识编辑器支持不可变历史、指定修订回填、字段 Diff 和不同运营人员提交新修订。
- Admin 新增 `/reply-readiness`，提供范围选择、风险汇总/筛选、逐题详情、运行历史、比较和治理跳转。

## 安全结果

- 完整一致的颗粒/尺寸证据可使符合政策的直接回答降为低风险。
- 30cm/40cm 冲突、估测颗粒数、缺失来源、跨 SKU 资料、真假授权无证据保持高风险。
- 库存、价格、实时物流、退款、改地址等政策题不能降为低风险。
- 问题集指纹、回答哈希、结果哈希、ReplyRule 快照和 Router 构建均验证；漂移失败关闭。
- 草稿不写正式 RAG、固定规则快照、Gateway、发送或 PDD。

## 数据与迁移

- C 新增 `reply_readiness_question_set_extensions` 与 `reply_readiness_runs` 两张任务专用表，迁移 `0023_reply_readiness_v1`。
- 迁移往返验证 `knowledge_materials` 列集合前后完全相同。
- 未迁移正式数据库；正式 Runtime 保持原状态。
- 原始 DOCX/XLSX/TXT、客户数据和真实商品资料未进入 Git；仓库只有脱敏分类和合成 Fixture。

## 契约兼容

- 正式共享 Contract 保持 `0.14.0 / coordinated`。
- 新类型仅为 `UNCOORDINATED_CANDIDATE`，附带 Schema、合成 Fixture、兼容说明和 A/C 解析测试。
- Gateway Wire 1.0 和冻结原始 Schema SHA-256 `fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80` 不变。

## 验证策略

- A：任务卡评测器、严格 HTTP Wire、Router/证据和候选契约定向回归。
- C：知识修订、问题集、幂等运行、失败账本、范围隔离、候选兼容和迁移往返定向回归。
- Admin：风险池、知识编辑器和导航定向测试、类型检查及本任务范围汇总回归。
- 生产 RAG 回答路径未修改，因此按任务卡约定不重复运行 28 题 RAG 评测。
- 未执行 Engine、CE、PDD 或其他仓 Full Gate。

最终 Gate 结果：

- A 汇总回归：`92 passed`；Python 编译检查通过。
- C 汇总回归：`21 passed`；`0023_reply_readiness_v1` 为单一源码 Head，Python 编译检查通过。
- Admin 汇总回归：`37 files / 93 tests passed`；`vue-tsc --noEmit` 通过。
- 候选 Schema/Fixture `--check` 通过；正式 Contract 为 `0.14.0 / coordinated`；Gateway 原始 Schema SHA-256 精确保持 `fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`。
- `git diff --check` 与 A/C machine-context JSON 解析通过。

## 不代表

本 Gate 只代表 AI-CS 仓内回答优化、历史修订和隔离风险池完成，不代表 `AI_CS_AUTOREPLY_READY`、Engine 自动发送、真实 PDD 验证、Pilot 或 Production 放量完成。

Entry Context 状态：`AI_CS_ENTRY_CONTEXT = DEFERRED_CROSS_REPO`。
