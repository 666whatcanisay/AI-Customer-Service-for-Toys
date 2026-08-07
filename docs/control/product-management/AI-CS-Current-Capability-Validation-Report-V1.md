# AI-CS Current Capability Validation Report V1

日期：2026-08-07

任务：R029

角色：AI-CS Production Simulation Analyst

报告状态：`PASS / AI_CS_CURRENT_CAPABILITY_VALIDATION_REPORT_READY`

下一阶段系统Gate：`CONDITIONAL / CUSTOMER_PC_SIMULATION_PREPARATION_REQUIRED`

真实PDD Gate：`BLOCKED / PDD_INTEGRATION_NOT_IMPLEMENTED`

> 本报告的`READY`只表示“当前能力测试报告已具备可复核证据”，不表示Channel Agent、PDD消息读取、浏览器控制或真实发送已经生产就绪。本轮未开发、未修改业务代码、数据库、RAG、Gateway Contract或Channel Engine，也未连接PDD或处理真实客户消息。

## 1. 当前架构状态

### 1.1 当前运行身份

| 项目 | 现场结果 |
| --- | --- |
| 产品版本 | `AI-CS V1.0.0` |
| Server Runtime版本 | `ai-cs-server-runtime.rc1` |
| Gateway版本 | `ai-cs-gateway.v1` |
| Gateway Contract | wire `1.0`；仓库协调版本`0.13.0 / coordinated` |
| 审计业务源码锚点 | 分支`codex/ai-cs-user-experience-acceptance-final-v1`，报告提交前clean `785cff1fbcc79e7110314615673df8d28ee491e6`；最终报告commit另行由Git解析 |
| 在线Runtime源码记录 | A/B/C/Admin均记录clean `2af974148e43c13736d63510fb7466658877a112` |
| 数据库版本 | R027隔离数据库`0016_production_hardening_v1`，`integrity_check=ok` |
| RAG | `test_knowledge_v031`，512维，70 embeddings，模型`qwen3.5:9b` |
| 网络模式 | `standard / LOCAL`，四服务仅监听`127.0.0.1` |
| 当前服务 | A `8420`、B `8421`、C `8422`、Admin `8423`均健康 |
| Gateway/Channel Agent | Gateway配置存在；Channel Agent集成默认关闭，Server URL未配置 |

### 1.2 当前启动方式

当前使用Windows受管启动体系和Git忽略的R027隔离配置：

- 入口：`scripts/windows/start_ai_customer_service.ps1`。
- 配置：`.runtime/r027-ux-acceptance-data-v1/ux-acceptance.local.ps1`。
- A/C：Uvicorn回环监听；B/Admin：预构建静态文件服务并通过固定同源代理访问A/C。
- 安全默认：LOCAL、禁止公网、不开浏览器、不开自动导入、不开自动知识同步、Channel Agent关闭。

### 1.3 运行身份风险

在线受管记录仍是`2af9741...`，审计业务源码锚点已是`785cff1...`。因此服务虽然健康，但不能把当前在线进程直接当作下一阶段的可追溯模拟基线。下一阶段启动前必须停止隔离服务，从一个clean且明确批准的SHA重新构建B/Admin并使用同一SHA启动四服务，再核对Runtime记录；不需要迁移、复制或改写R027数据。

Gateway canonical schema SHA-256为`FEF35AFB67DCD5027D7AA59FF35E5B6035A4130C5C1957AB41D4397D5FA67B80`，AI-CS与Channel Engine的Contract目录均无改动；本轮Contract测试`15 passed`。

## 2. 当前数据选择

本轮仅读取文件元数据、表结构与聚合数量，没有输出账号凭据、客户内容、知识原文或向量内容。

### 2.1 数据库候选

| 候选 | Revision | IAM | 业务数据 | 知识/AI证据 | 结论 |
| --- | --- | --- | --- | --- | --- |
| R027隔离Runtime | `0016` | 5用户、3角色、3绑定 | 2店铺、24商品、18 SKU、19 FAQ | 2资料、5发布收据、37发布chunks、63解析、5 AI事件 | 最完整，推荐 |
| R027 source baseline / phase-e standard | `0013` | 3用户、3角色、1绑定 | 2店铺、24商品、18 SKU、16 FAQ | 1资料、3收据、9 chunks、5 AI事件 | 可回滚参照，不作本次主数据 |
| R006.2 acceptance | `0011` | 无用户体系 | 2店铺、24商品、18 SKU、16 FAQ | 3收据、9 chunks、1 AI事件 | 缺IAM与新Workspace状态 |
| shadow | `0008` | 无用户体系 | 1店铺、5商品、18 SKU、16 FAQ | 旧能力 | 数据较少，不推荐 |
| formal最新备份 | `0012` | 无现行IAM | 2店铺、24商品、18 SKU、16 FAQ | 3收据、9 chunks | 用于保护/恢复，不用于本次模拟 |

注：R027当前有5个用户，只对已批准的验收角色做过登录证据核对；报告不展开额外账号身份。当前数据内`ai_response_feedback`为0，表示Feedback能力已有源码和自动测试证据，但这套隔离数据尚未形成问题反馈样本，不能把“接口存在”写成“已有业务反馈数据”。

### 2.2 RAG候选

| 候选 | 集合 | Embeddings | 完整性 | 结论 |
| --- | --- | ---: | --- | --- |
| R027隔离Runtime | `test_knowledge_v031` | 70 | Chroma SQLite完整、512维 | 推荐，并与R027数据库成对使用 |
| R027 source baseline / phase-e standard | 同名 | 56 | 完整 | 回滚参照 |
| phase-e较早快照 | 同名 | 47 | 完整 | 历史参照 |
| R006.2 / repository vector_db | schema存在 | 0 | 无有效embedding | 不适合AI流程验收 |

### 2.3 推荐选择

- 数据库：`.runtime/r027-ux-acceptance-data-v1/runtime/platform.sqlite3`
- RAG：`.runtime/r027-ux-acceptance-data-v1/runtime/vector-db`
- 集合：`test_knowledge_v031`，70 embeddings

理由：该组合revision最高，IAM、店铺、商品、SKU、FAQ、发布收据、上下文解析与AI事件最完整；已针对缺件问题完成受控检索，返回6条依据、人工转接、高风险和禁止自动发送提示。它只能作为本机隔离验收数据，不得替代正式数据库/RAG，也不得同步、重建或复制到生产。

## 3. Windows Client状态

### 3.1 候选包

| 项目 | 结果 |
| --- | --- |
| 产品 | AI-CS Channel Agent Windows Client |
| 版本 | `1.1.1`，`ChannelAgent.exe version`退出码0 |
| ZIP | `AI-CS-Channel-Agent-1.1.1-windows-x64.zip`，22,129,632 bytes |
| ZIP SHA-256 | `BAF17B07469A8E5FFD274A473BE60412AE22AC04A483D52C8F69A39E48CEB1FA` |
| EXE SHA-256 | `C3D6C0BC3AAD98B93F76B7BDA28AD2B46755E3C1C5C8E3CDBB875503AD996FC9` |
| 数字签名 | `NotSigned` |
| 当前安装 | `%LOCALAPPDATA%\Programs\AI-CS\ChannelAgent`不存在 |
| 当前运行 | 未发现ChannelAgent进程或默认数据目录 |
| 来源仓库 | `main@673ce7e1e89cca977463e2e98cec8d00055a6e98`，但有27项dirty记录 |

### 3.2 安装与启动

- 安装：解压受控ZIP后使用`packaging/windows-client-v1/Install-AI-CS-Channel-Agent.ps1`；默认安装在当前用户LOCALAPPDATA，不应把凭据写入命令行或仓库。
- 启动与诊断：`ChannelAgent.exe check-config`、`start`、`status`、`stop`、`version`。
- 可选自启动：`ChannelAgent.exe autostart enable|disable`，需单独验收登录后行为。

### 3.3 是否可作为当前电脑模拟

结论：`CONDITIONAL YES`。当前电脑可用于模拟“安装、配置、注册/绑定、心跳、在线/离线状态、重连”流程，但还不能模拟PDD客户消息读取或真实发送。

启动前必须先关闭以下条件风险：

1. 把Channel Agent 1.1.1来源变更形成clean、可追溯的受控候选；禁止直接从当前27项dirty仓库宣称RC。
2. 对EXE进行公司认可的代码签名，或在隔离测试中对未签名风险做显式批准；真实客服电脑不应长期运行未签名二进制。
3. 安装后创建外置Runtime配置，连接受控的Channel Engine测试地址；当前AI-CS自身的Channel Agent集成仍关闭。
4. 对ZIP/EXE再次核对上述hash，并保留不含凭据的安装、启动、心跳与卸载证据。

### 3.4 当前明确缺失

Agent 1.1.1的远程能力在类型和运行时均固定为：`message_read_enabled=false`、`send_enabled=false`、`browser_automation_enabled=false`。这意味着它目前是设备身份与连接客户端，不是PDD Adapter，也不是消息监听/发送客户端。

## 4. 当前可运行能力

| 能力 | 状态 | 证据边界 |
| --- | --- | --- |
| 用户登录/首次改密/退出 | 已完成 | R027四个批准账号的真实HTTP登录、改密、Session撤销已验证 |
| RBAC与权限隔离 | 已完成 | ADMIN、OPERATOR、CUSTOMER_SERVICE正负向验证通过 |
| 店铺绑定与默认店铺 | 已完成 | 客服可绑定/切换授权店铺；运营/管理员按全店范围处理 |
| 商品与SKU | 已完成 | 当前数据库24商品、18 SKU；Workspace可自动解析并允许人工确认 |
| RAG知识检索 | 已完成（隔离数据） | 70 embeddings；缺件问题有6条依据 |
| AI回复建议 | 已完成（人工确认边界） | 有回复、依据、风险；不自动发送 |
| Feedback能力 | 源码/测试完成 | 采用、修改、拒绝、标记问题链路有测试；当前R027反馈表0记录 |
| Workspace人工会话 | 可模拟 | 可人工新建去标识会话、生成或直接输入回复 |
| Agent设备状态 | 源码/测试完成，当前未接入 | Workspace有facade与状态UI；Runtime集成关闭 |
| Gateway Decision/Health | 已实现且Contract保护通过 | 本轮不连接生产Engine，Contract测试15 passed |

## 5. 当前缺失能力

| 能力 | 当前结论 | 影响 |
| --- | --- | --- |
| 真实PDD登录/授权 | 未完成 | 无法建立合法、稳定的平台会话 |
| PDD Adapter | 有发现/治理/观察设计资产，不等于生产实现 | 没有批准的真实页面/协议适配器 |
| Message Listener | 未完成且开关固定关闭 | Workspace不会自动收到PDD客户消息 |
| Browser Control | 未完成且Agent开关固定关闭 | 无法稳定识别会话、商品卡片、风控/CAPTCHA状态 |
| Send Executor | 真实发送关闭 | 人工确认后仍没有渠道发送执行与回执 |
| 消息幂等与投递回执 | 未形成真实平台闭环 | 无法证明不重复发送、最终成功或失败原因 |
| 客服电脑正式安装包 | 候选未签名、来源dirty | 不能直接广泛部署 |
| 第二电脑/LAN E2E | 本轮未执行 | 当前R027仅LOCAL，无法证明跨机连通 |

## 6. 下一阶段真实客服模拟计划

下一阶段应先做“设备与AI辅助流程模拟”，明确不冒充PDD端到端：

1. **冻结身份**：将AI-CS与Channel Agent分别固定到clean SHA；核对Agent ZIP/EXE hash。
2. **重启隔离AI-CS**：继续使用R027数据库/RAG，在同一批准SHA下重新构建并启动A/B/C/Admin，确认四条Runtime记录SHA一致。
3. **安装Agent**：在当前电脑用受控安装脚本安装1.1.1，使用独立数据目录，不携带生产secret。
4. **启动测试Engine**：仅回环或受控LAN，保持`real_send_enabled=false`、kill switch开启、人工批准开启。
5. **设备注册/绑定**：Agent启动→生成/输入一次性绑定信息→管理员激活→心跳ONLINE→Workspace显示设备和当前店铺。
6. **人工注入会话**：因为没有Message Listener，由测试人员在Workspace创建去标识测试会话并输入“这个积木缺件怎么办？”。
7. **AI辅助**：Store/Product/SKU解析→AI生成建议→展示知识依据与风险→客服人工确认。
8. **止于确认**：记录采用/修改/拒绝，不执行PDD发送；若需要展示渠道动作，仅使用Fake/Mock并明确标识。
9. **异常演练**：Agent离线、Engine不可达、权限失效、店铺不匹配；验证中文提示、fail closed、恢复后心跳。
10. **证据收集**：版本、SHA/hash、配置摘要、状态、时间线、测试结果和卸载/回滚；不采集凭据、客户内容或完整日志。

目标流程表达为：

`启动EXE → Agent上线 → 绑定账号/设备 → 选择或自动进入授权店铺 → Workspace → 人工测试消息 → AI建议 → 人工确认 → 记录结果（不发送）`

## 7. 需要人工参与的位置

### 必须人工

- 批准未签名候选仅用于隔离测试，或完成正式代码签名后再安装。
- 安装/卸载确认，以及Windows防火墙或安全软件提示处理；禁止自动关闭防火墙。
- 登录AI-CS、首次改密、选择/确认店铺。
- 输入一次性绑定信息；管理员完成独立设备激活。
- 在当前无Message Listener阶段创建去标识测试会话。
- 审阅AI建议、商品/SKU识别、知识依据和风险；选择采用、修改、拒绝或转人工。
- 未来PDD阶段：扫码/验证码/风控确认、CAPTCHA处理、最终发送确认和异常处置。

### 可自动化

- Git SHA/clean、包hash、版本和配置结构检查。
- AI-CS/Engine/Agent health、心跳、在线/离线与重连监控。
- Contract、RBAC、权限负面、数据库完整性和RAG数量检查。
- 去敏运行日志、状态时间线、失败分类和报告汇总。
- 超时、权限失效、协议漂移时的fail-closed告警；不能自动改配置或绕过授权。

## 8. PDD接入准备清单

### 已经具备

- AI-CS用户、Session、RBAC、店铺范围、商品/SKU上下文、RAG、AI回复、风险/依据与Feedback基础。
- Gateway V1 Decision/Health、HMAC、timestamp、nonce、幂等与Error Envelope。
- Channel Engine RC1安全治理资产：kill switch、人工批准、真实发送默认关闭。
- Channel Agent设备身份、安装候选、绑定、心跳、状态与重连基础。
- Workspace坚持人工确认，不自动发送消息。

### 未具备

- 获得授权并可维护的真实PDD登录/会话机制。
- 可验证的PDD Adapter生产选择器/协议映射。
- 稳定的会话列表与客户消息监听。
- 受控浏览器运行时、专用Profile、版本/选择器漂移检测。
- 人工批准后的真实Send Executor、幂等、回执、重试和失败补偿。
- CAPTCHA/风控/掉线/多店铺切换的真实异常闭环。
- 已签名、clean、可回滚的Channel Agent安装RC与第二电脑实机E2E。

### 需要开发并独立Gate

1. **PDD Adapter**：只读发现→观察验证→受控激活；所有页面/协议字段版本化，出现漂移立即停用。
2. **Browser Control**：专用Edge/Chrome Profile、人工扫码、窗口/店铺身份校验、最小权限和防误操作边界。
3. **Message Listener**：去重游标、会话/消息稳定ID、Store映射、断线续读、客户内容最小化与审计保留策略。
4. **Send Executor**：只接受已人工批准Decision；强幂等、发送前二次店铺/会话核对、回执、超时未知状态处理和全局kill switch。
5. **Integration Gate**：先Fake/沙箱，再Observe Only，再单店单客服、低量真实试点；每阶段独立回滚，不允许一次开启自动登录、读取和发送。

## 9. 验证记录与最终判定

| 检查 | 结果 |
| --- | --- |
| AI-CS四服务健康 | PASS：8420/8421/8422/8423 |
| SQLite完整性 | PASS：推荐数据库`integrity_check=ok` |
| RAG完整性/数量 | PASS：推荐集合70 embeddings |
| Agent版本 | PASS：1.1.1可执行 |
| Agent安装/运行 | NOT RUNNING：当前未安装、未启动 |
| Agent供应链 | BLOCKED：未签名且来源仓库dirty |
| Gateway Contract保护 | PASS：canonical SHA未变，15 tests passed |
| 运行身份一致性 | BLOCKED FOR NEXT START：在线记录2af9741，审计业务源码锚点785cff1 |
| PDD/消息读取/浏览器/发送 | NOT IMPLEMENTED / DISABLED |

最终结论：AI-CS现有业务能力和R027隔离数据足以准备下一阶段的**单机客服电脑受控模拟**；开始前必须先统一AI-CS运行SHA、冻结并签名Channel Agent候选。真实PDD接入仍为BLOCKED，必须按PDD Adapter、Browser Control、Message Listener、Send Executor四个独立工作包开发和验收。

Final Status: `AI_CS_CURRENT_CAPABILITY_VALIDATION_REPORT_READY`
