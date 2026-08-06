# AI-CS Current Requirement Status Summary

> 快照日期：2026-08-06
>
> 唯一需求事实来源：[AI-CS Requirement Registry V1](AI-CS-Requirement-Registry-V1.md)
>
> 当前 Gate：`AI_CS_ACCOUNT_POLICY_READY / AI_CS_INITIAL_ACCOUNTS_BLOCKED / AI_CS_USER_MANAGEMENT_READY / GATEWAY_LAN_MODE_READY / AI_CS_INTERNAL_PRODUCTION_READY / R003_PILOT_ACCEPTANCE_PENDING`

本文件是状态快照，不是第二份需求台账。

## 1. 状态统计

| 状态 | 数量 | 需求 |
| --- | ---: | --- |
| `DONE` | 14 | R001、R002、R004、R006、R008、R009、R010、R011、R012、R013、R014、R015、R016、R018 |
| `IN_PROGRESS` | 1 | R003 |
| `TODO` | 1 | R005 |
| `BLOCKED` | 2 | R007、R017 |
| `DEPRECATED` | 0 | 无 |
| 合计 | 18 | R001–R018 |

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
| R016 | AI-CS User Management & Store Binding V1 | `DONE` | C提供真实登录、opaque session、固定RBAC、Store绑定和Workspace facade；B/Admin使用服务端身份，A管理端点向C验权并透传凭证。 | 受控部署0013、交互创建首个ADMIN，并用三类非生产账号执行浏览器验收。 |
| R017 | AI-CS Initial Production Accounts V1 | `BLOCKED` | Runtime仍为0012/pre-IAM，IAM表不存在；R018已解决账号格式、首次改密、客服多店和运营/管理员全店策略，但源码尚未受控部署且账号仍未创建。 | 单独授权源码固化、备份/0013协调迁移/Runtime切换，再交互执行初始化和真实三角色验收。 |
| R018 | AI-CS Account Policy Adjustment V1 | `DONE` | Contracts 0.10、C IAM、B/Admin流程、A鉴权桥和Windows初始化脚本已实现并通过全量回归；临时口令值未硬编码或记录。 | 协调部署B/C/Admin/A鉴权桥后解除R017的部署阻塞；不得把源码Ready误报为账号Ready。 |

## 3. 当前主阻塞

R006实现与正式发布阻塞均已关闭。C保存并裁决`data_source/customer_service_status`，提供`/customer-service/catalog/**`最终投影；B只消费投影。正式只读API和浏览器Smoke证明PILOT+DISABLED记录不会清空其他目录，TEST数据连续可用。

V1.0.0内部生产正式基线位于`release/ai-cs-v1.0.0`，功能正式化提交为`9f2b500dc0d6469a04a6953b7886d65e34412a22`，正式文案补丁为`9911ba67cef330a7a1b4f03f82de227cbee6982d`，防复发测试为`0f230c6f50f8b6162c4e52f3b167053e6592c656`；正式标签为`ai-cs-v1.0.0`，精确SHA从Git与Runtime记录解析。Contracts为0.5.0，数据库为`0012_internal_production_finalization_v1`且完整性正常。四服务正式版本在5173/5174/8000/8011以standard/LAN通过；活动集合内部物理名仍为`test_knowledge_v031`、56 chunks，模型`qwen3.5:9b` ready。

R011在当前开发分支上将源码contracts增量提升为0.6.0并建立Gateway Foundation；它尚未部署到上述V1.0.0 Runtime，未配置生产Engine或生产credential，也没有改变0012、RAG与四服务既有运行事实。Gateway默认关闭，正式启用必须经过独立Deployment Gate。

R012当时只整理并验证dirty Candidate，没有修改Gateway实现或contracts，也没有创建commit/tag/push；保护锚点`0b3367f85999f1dc840accf23742c290eb53746b`在该Gate时仍是HEAD。R014已将其作为直接父提交保留并形成受控RC；Source Baseline Ready本身仍不表示已部署或生产联通。

R014已关闭上述dirty source阻塞：保护锚点成为source commit `6ae8d407...`的直接父提交，Windows PowerShell 5.1修复后的代码RC为`4b6c0bd0...`。四服务从该clean SHA启动并完成Gateway/Console/Decision/stop验证；该事实仍不表示远端发布、TLS、正式secret manager或生产Channel Engine联通。

R016已完成源码和自动化Gate：数据库迁移前进到0013，复用既有Store；浏览器身份从tester identity切换为C签发的opaque session，角色和店铺由服务端裁决。该Gate不表示已迁移正式数据库或已创建生产账号；部署必须先备份、迁移，再通过交互式CLI创建首个ADMIN并完成角色验收。

R017只读审计证明上述部署步骤尚未发生：受控数据库仍为0012，IAM表缺失，运行身份端点404。本轮数据库、账号、Session和绑定均为零写入，当前不能声明初始账号Ready。

R018已经关闭R017发现的源码策略输入缺口：Unicode/大小写显示用户名与批准的8字符临时初始化值可进入强制首次改密流程；客服可自选多个已启用客服Store，运营和管理员由角色获得全Store。Contracts为`0.10.0 / coordinated`，B/C/Admin/A鉴权桥必须同批部署；正式Runtime仍未迁移，三个初始账号仍未创建。

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
R016 User Management DONE（IAM源码与自动化Gate，受控部署待执行）
  ↓
R018 Account Policy DONE（0.10协调源码与初始化脚本，生产执行待R017）
  ↓
R003业务结果验收
  ↓
R005真实Pilot验证
```

Prompt、R009导入逻辑、Import Center和B客服核心业务流程未修改。本次正式化和浏览器Smoke不能替代R003全量业务验收或R005真实运行验证；R007继续由网络侧处理。当前`origin`为本地历史保护仓库，没有远端发布声明。
