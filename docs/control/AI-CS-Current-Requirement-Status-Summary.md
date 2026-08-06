# AI-CS Current Requirement Status Summary

> 快照日期：2026-08-06
>
> 唯一需求事实来源：[AI-CS Requirement Registry V1](AI-CS-Requirement-Registry-V1.md)
>
> 当前 Gate：`AI_CS_PRODUCTION_RC_READY / CONTROLLED_DEPLOYMENT_PENDING / R003_PILOT_ACCEPTANCE_PENDING`

本文件是状态快照，不是第二份需求台账。

## 1. 状态统计

| 状态 | 数量 | 需求 |
| --- | ---: | --- |
| `DONE` | 22 | R001、R002、R004、R006、R008、R009、R010、R011、R012、R013、R014、R015、R016、R017、R018、R019、R020、R021、R022、R023、R024、R025 |
| `IN_PROGRESS` | 1 | R003 |
| `TODO` | 1 | R005 |
| `BLOCKED` | 1 | R007 |
| `DEPRECATED` | 0 | 无 |
| 合计 | 25 | R001–R025 |

## 2. 当前需求状态

| ID | 名称 | 状态 | 当前事实 | 下一 Gate |
| --- | --- | --- | --- | --- |
| R001 | C商品知识运营中心V2 | `DONE` | 正式基线已包含商品知识结构、模板、状态和知识缺口。 | 不重做结构。 |
| R002 | AI客服反馈沉淀闭环 | `DONE` | B/C/contracts工程闭环已进入正式基线。 | 真实效果转R005。 |
| R003 | C新增店铺/商品无法进入B客服 | `IN_PROGRESS` | R006.1已正式发布，指定PILOT商品已在正式Runtime完成人工发布、启用、B选择和A同商品引用回答。 | 执行完整PILOT业务结果验收后决定是否关闭。 |
| R004 | AI-CS运行版本统一 | `DONE` | 正式目录、Runtime身份和回滚锚点已统一。 | 保持运行基线。 |
| R005 | Customer Feedback Loop真实运行验证 | `TODO` | 尚无真实客服运行后的改善证据。 | R003关闭后开展受控Pilot。 |
| R006 | Pilot Business Data Activation V1 | `DONE` | R006.1已正式发布；R006.2焦点刷新、60秒低频检查、待启用计数和筛选全选已纳入V1.0.0内部生产正式基线并通过回归。 | 保持C唯一Owner，不得混入B可信度判断。 |
| R007 | 网络环境导致客服无法访问5173 | `BLOCKED` | 属公司网络/VLAN/端口策略。 | 网络侧第二终端验收。 |
| R008 | Project Structure Simplification V1 | `DONE` | `AI-CS/`成为正式运行与后续开发目录；Recovery保留回滚。 | 旧Worktree另行归档。 |
| R009 | 商品知识采集模板导入 V1 | `DONE` | 实现、浏览器验收及正式0009能力已进入当前0012运行链，后续迁移未改变R009逻辑或删除数据。 | 保持Import Center和导入边界。 |
| R010 | AI-CS Production Finalization V1 | `DONE` | V1.0.0正式文案、来源正式化、测试入口隔离、contracts 0.5.0、0012及全量回归均完成。 | 以`ai-cs-v1.0.0`作为稳定标签；不把本地保护origin误报为远端发布。 |
| R011 | AI-CS Gateway Server Foundation V1 | `DONE` | 独立Gateway Decision/Health、HMAC、防重放、严格V1、ErrorEnvelope和持久化幂等已完成；B、`/api/chat`、RAG与商品知识不变。 | 独立部署Gate完成TLS、secret托管和非生产Engine集成后才能考虑生产连接；Receipt/Event另立任务。 |
| R012 | AI-CS Gateway Source Baseline V1 | `DONE` | Candidate已冻结为单实例、人工审批、默认关闭的Production MVP源码输入；Deferred/Experimental、文件边界、Contract缺口与T4输入已记录，后由R014受控提交。 | 保持保护锚点祖先关系；后续只做非生产集成，不得直连生产。 |
| R013 | AI-CS Production Server Runtime RC V1 | `DONE` | Production wrapper、secret reference、签名Health Gate、Console Server/Gateway/Contract状态与回归已完成；源码已由R014提交。 | 另行执行push/tag/artifact、TLS/access control、正式secret manager和非生产跨进程E2E；不得直连生产。 |
| R014 | AI-CS Server Release Candidate Stabilization V1 | `DONE` | dirty Candidate已形成source `6ae8d407...`与PowerShell 5.1修复后的clean code RC `4b6c0bd0...`；Windows start/status/Decision/Console/stop通过。 | 另行授权push/tag/artifact、正式secret manager/TLS与非生产Engine E2E；不得直连生产。 |
| R015 | AI-CS Gateway LAN Mode Enablement V1 | `DONE` | LOCAL与受控RFC1918 LAN Gateway模式已实现；A Core/C/Admin保持loopback，Gateway HMAC和wire 1.0不变。 | 管理员配置精确Private防火墙规则并由独立客服电脑验收；不可信网络前增加TLS。 |
| R016 | AI-CS User Management & Store Binding V1 | `DONE` | C提供真实登录、opaque session、固定RBAC、Store绑定和Workspace facade；0013已进入正式Runtime。 | 维持服务端授权与定期安全审计。 |
| R017 | AI-CS Initial Production Accounts V1 | `DONE` | 三个批准账号已创建，真实登录、首次改密、Session、RBAC与Store范围通过。 | 三人首次正式使用立即设置各自长期口令。 |
| R018 | AI-CS Account Policy Adjustment V1 | `DONE` | Contracts 0.10、C IAM、B/Admin流程、A鉴权桥和Windows初始化脚本已实现、回归并部署。 | 保持协调版本，不回退到0.9单默认店策略。 |
| R019 | AI-CS Production IAM Deployment & Initial Accounts V1 | `DONE` | clean source、正式备份、0013、三账号、0 active sessions、0客服固定绑定与回滚证据全部通过。 | 日常密码轮换/停用/审计；R003/R007仍独立。 |
| R020 | AI-CS Store Context Resolver V1 | `DONE` | 默认Store、C权威Product/SKU解析、`resolution_id`上下文注入和最小Admin审计完成；0014仅隔离验证。 | 另行备份并部署0014与协调B/C/Admin；不得把Source Ready冒充Runtime已部署。 |
| R021 | AI-CS Customer Workspace Production V1 | `DONE` | B三栏生产工作流、客服/会话状态、AI依据/风险、采用/修改/拒绝原因/问题标记及幂等失败恢复完成；不接真实渠道。 | 随R020协调部署0014/C/B；真实渠道会话持久化必须另立授权任务。 |
| R022 | AI-CS Customer Desktop Workflow Integration V1 | `DONE` | B显示真实客服/店铺/设备及Agent在线、版本、心跳；C提供鉴权facade、一次性绑定授权和最小审计，Engine保持不变。 | 备份后协调部署0014/0015、contracts/C/B并配置非生产Engine；第二台客服电脑E2E后再决定生产启用。 |
| R023 | AI-CS Code Quality Audit V1 | `DONE` | 只读审计登记22项；审计Gate就绪，但存在P0/P1、B测试红灯、dirty source与0013/0015不一致。 | 按报告拆分Remediation任务卡；全部P0/P1关闭并形成clean RC前禁止生产发布。 |
| R024 | AI-CS Production Hardening V1 | `DONE / SOURCE_ONLY` | R023 P0/P1源码关闭；全域回归全绿，正式DB保持0013，Gateway/RAG指纹不变。 | 精确形成clean RC，配置TLS并受控迁移0014–0016后做同SHA部署验收。 |
| R025 | AI-CS Production Release Candidate Freeze V1 | `DONE` | R020–R024形成clean Release branch/commit/tag；迁移可逆、全域Gate通过、正式DB保持0013。 | 按Deployment Checklist配置TLS/secret/WMI，备份并迁移0014–0016，执行同SHA部署验收。 |

## 3. 当前主阻塞

R006实现与正式发布阻塞均已关闭。C保存并裁决`data_source/customer_service_status`，提供`/customer-service/catalog/**`最终投影；B只消费投影。正式只读API和浏览器Smoke证明PILOT+DISABLED记录不会清空其他目录，TEST数据连续可用。

V1.0.0原始内部生产基线位于`release/ai-cs-v1.0.0`，功能正式化提交为`9f2b500dc0d6469a04a6953b7886d65e34412a22`；R019在`release/product-reliability-hardening-v1`上将当前正式Runtime受控前进到contracts `0.10.0 / coordinated`和数据库`0013_user_management_v1`，完整性正常。四服务在5173/5174/8000/8011以standard/LOCAL完成IAM部署验收；活动集合内部物理名仍为`test_knowledge_v031`、56 chunks，模型`qwen3.5:9b` ready。LAN仍由独立网络Gate管理。

R011在当前开发分支上将源码contracts增量提升为0.6.0并建立Gateway Foundation；它尚未部署到上述V1.0.0 Runtime，未配置生产Engine或生产credential，也没有改变0012、RAG与四服务既有运行事实。Gateway默认关闭，正式启用必须经过独立Deployment Gate。

R012当时只整理并验证dirty Candidate，没有修改Gateway实现或contracts，也没有创建commit/tag/push；保护锚点`0b3367f85999f1dc840accf23742c290eb53746b`在该Gate时仍是HEAD。R014已将其作为直接父提交保留并形成受控RC；Source Baseline Ready本身仍不表示已部署或生产联通。

R014已关闭上述dirty source阻塞：保护锚点成为source commit `6ae8d407...`的直接父提交，Windows PowerShell 5.1修复后的代码RC为`4b6c0bd0...`。四服务从该clean SHA启动并完成Gateway/Console/Decision/stop验证；该事实仍不表示远端发布、TLS、正式secret manager或生产Channel Engine联通。

R016/R018协调源码已经由R019部署：正式数据库在迁移前完成可恢复备份，当前为0013且完整性ok。三个批准账号已创建并通过真实登录、强制首次改密、Session撤销和服务端RBAC；客服可选择两个启用Store并已恢复0固定绑定，运营/管理员为角色级全Store。最终0 active sessions，未记录凭证、hash或token。

R020源码在该基础上建立唯一默认Store和C权威Conversation Context Resolver。正式Runtime仍为0013；0014只完成隔离往返验证，因此下一次标准启动前必须先做正式SQLite备份并按协调版本部署B/C/Admin。Gateway与RAG基线未变。

R021在不增加接口或连接渠道的边界内，把B收敛为三栏连续客服工作流。Production build不预置验收会话；人工输入仅留页面内存，客服采用后仍需在外部渠道人工处理并显式完成。该Source Gate依赖R020的0014 Provider，不能冒充当前正式Runtime已部署。

R022在上述人工工作流上增加受控设备关联：浏览器只访问C同源facade，C以真实session和Store scope关联Engine投影；自助grant仅用于已注册`UNBOUND`精确设备，独立activation仍为强制步骤。正式Runtime仍为0013，0014/0015和Channel Agent生产配置均未部署，因此该Gate只表示源码、契约与隔离回归就绪。

R023已完成全仓生产上线前审计。审计本身为DONE，但生产发布判定为`FAIL / PRODUCTION_RELEASE_BLOCKED`：内部知识投影鉴权、TLS/生产Web承载、Session撤销、登录限流、RAG失败语义、发布并发、C日志、B红灯和CI覆盖等P1以及dirty source/P0尚未关闭。

R024已关闭上述P0/P1源码阻断：内部服务鉴权、Session/登录防护、生产TLS静态Web、RAG非2xx、发布租约、去敏日志、CI和时钟稳定性均有回归证据。当前Gate是Source Hardening Ready；仓库仍dirty且正式Runtime保持0013，因此clean RC、正式迁移与同SHA部署仍是后续独立Gate。

R025已将R020–R024候选精确固化为`ai-cs-production-rc-v1`：工作树clean、迁移链线性可逆、全域测试/构建/安全Gate通过，Gateway/RAG/Channel/PDD边界保持。当前可以进入受控Deployment Gate，但正式数据库、TLS、防火墙和真实外部联通尚未改变。

历史初始化Store已按审计规则从TEST正式化为`INITIAL_IMPORT`，当前Store矩阵为`INITIAL_IMPORT + ENABLED=1`、`PILOT + ENABLED=1`；Product状态、activation receipt、发布记录、chunks和embeddings均未删除或重建。浏览器验证Admin正式页面与六模板入口，B已发布商品显示3 chunks/3 citations并保持人工确认、不自动发送/退款/改订单边界。

## 4. 执行顺序

```text
R006 Production Release COMPLETE
  ↓
R006.1 Production Release COMPLETE
  ↓
R006.2 Experience Implementation COMPLETE
  ↓
R010 Production Finalization DONE
  ↓
R011 Gateway Server Foundation DONE（源码就绪，未连接生产）
  ↓
R012 Gateway Source Baseline DONE（分类/范围/T4输入冻结）
  ↓
R013 Production Server Runtime RC DONE（wrapper/config/Console）
  ↓
R014 Server Release Candidate Stabilization DONE（clean commit + Windows Runtime Gate）
  ↓
R015 Gateway LAN Mode DONE（受控LAN源码，跨机部署验收待执行）
  ↓
R016 User Management DONE（IAM源码与正式0013部署完成）
  ↓
R018 Account Policy DONE（0.10协调源码与初始化脚本已部署）
  ↓
R019 Production IAM Deployment DONE（备份/0013/三账号/真实验收）
  ↓
R020 Store Context Resolver DONE（源码/契约/隔离0014；待部署）
  ↓
R021 Customer Workspace Production DONE（B源码工作流；待随R020协调部署）
  ↓
R022 Customer Desktop Workflow Integration DONE（B/C/contracts/OPS源码；生产Engine未连接）
  ↓
R023 Code Quality Audit DONE（审计完成；Production Release BLOCKED）
  ↓
R024 Production Hardening DONE / SOURCE_ONLY（P0/P1源码关闭）
  ↓
R025 Production RC Freeze DONE（clean branch/commit/tag）
  ↓
controlled migration/deployment validation
  ↓
R003业务结果验收 / R005真实Pilot验证
```

Prompt、R009导入逻辑、Import Center和B客服核心业务流程未修改。本次正式化和浏览器Smoke不能替代R003全量业务验收或R005真实运行验证；R007继续由网络侧处理。当前`origin`为本地历史保护仓库，没有远端发布声明。
