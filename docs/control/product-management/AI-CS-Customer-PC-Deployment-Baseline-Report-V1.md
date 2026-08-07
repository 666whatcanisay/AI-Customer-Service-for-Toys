# Customer PC Deployment Baseline Report V1

日期：2026-08-07

任务：R030 AI-CS Customer PC Deployment Preparation V1

角色：AI-CS Customer PC Deployment Engineer

Phase 1 Gate：`FAIL / AI_CS_CUSTOMER_PC_DEPLOYMENT_BLOCKED_BASELINE_IDENTITY_MISMATCH`

目标状态：`AI_CS_CUSTOMER_PC_DEPLOYMENT_READY`（本轮未达到）

> 本报告只记录部署前身份冻结证据。根据任务硬门禁，发现AI-CS当前Git SHA与在线Runtime SHA不一致后，已停止Phase 2–5。没有停止或重启现有服务，没有修改Channel Engine，没有安装或启动Channel Agent，没有输入密码、执行授权、绑定用户/店铺或连接PDD。

## 1. Gate结论

当前不能进入真实客服电脑部署流程，原因如下：

1. **AI-CS源码与在线Runtime身份不一致**：当前Git HEAD为`51da46fa1748bf806fcc18530778f7b26ac5844f`，四个在线服务记录均为clean `2af974148e43c13736d63510fb7466658877a112`。
2. **Channel Agent来源不是clean候选**：Engine仓库`main@673ce7e1e89cca977463e2e98cec8d00055a6e98`存在27项dirty记录。
3. **客户端供应链尚未达到客服电脑标准**：1.1.1 EXE未签名；本机未安装、未运行，尚无正式安装/配置/Heartbeat证据。

数据库与RAG选择本身通过：R027隔离数据库为0016且完整，活动集合为`test_knowledge_v031` 70 embeddings。它们不解除源码/Runtime身份门禁。

## 2. AI-CS基线

### 2.1 Git与工作树

| 项目 | 现场结果 |
| --- | --- |
| Repository | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS` |
| Branch | `codex/ai-cs-user-experience-acceptance-final-v1` |
| Git HEAD | `51da46fa1748bf806fcc18530778f7b26ac5844f` |
| 检查前状态 | clean；R029报告已提交 |
| 当前未提交范围 | 仅本次R030任务卡/报告与治理状态文档；无业务源码变化 |
| Gateway canonical SHA-256 | `FEF35AFB67DCD5027D7AA59FF35E5B6035A4130C5C1957AB41D4397D5FA67B80` |

### 2.2 在线Runtime

| 服务 | 端口 | Health | 记录SHA | 记录状态 |
| --- | ---: | --- | --- | --- |
| A / RAG | 8420 | HTTP 200 | `2af974148e43c13736d63510fb7466658877a112` | CLEAN |
| B / Customer Web | 8421 | HTTP 200 | 同上 | CLEAN |
| C / Platform API | 8422 | HTTP 200 | 同上 | CLEAN |
| Admin Web | 8423 | HTTP 200 | 同上 | CLEAN |

四个记录的`repository_source_fingerprint`均为`35776bf81bcf19932965bfde101b535ed3c7b8eb8e7ff9f8bedc5dee82b4ee75`，运行方式为`standard / LOCAL`。服务健康只能证明进程可用，不能证明它们与当前部署源码一致。

### 2.3 数据库与RAG

| 项目 | 现场结果 |
| --- | --- |
| Database | `.runtime/r027-ux-acceptance-data-v1/runtime/platform.sqlite3` |
| Revision | `0016_production_hardening_v1` |
| SQLite完整性 | `ok` |
| Database大小 | 2,023,424 bytes（在线WAL环境只记录大小，不计算静态文件hash） |
| RAG数据库 | `.runtime/r027-ux-acceptance-data-v1/runtime/vector-db/chroma.sqlite3` |
| RAG完整性 | `ok` |
| 活动集合 | `test_knowledge_v031` |
| 维度/数量 | 512 / 70 embeddings |
| 历史主集合 | `documents`，0 embeddings（按现有设计保留，不重建） |

R027数据选择与任务输入一致。本轮通过只读SQLite连接检查，没有迁移、同步、发布、清空、重切片或重新embedding。

## 3. Channel Agent基线

### 3.1 来源状态

| 项目 | 现场结果 |
| --- | --- |
| Repository | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-Channel-Execution-Engine` |
| Branch | `main` |
| HEAD | `673ce7e1e89cca977463e2e98cec8d00055a6e98` |
| 工作树 | DIRTY，27项 |
| 已跟踪修改 | `pyproject.toml`、Engine app/RBAC/ORM共4项 |
| 未跟踪范围 | Agent源码、绑定API、Windows packaging、脚本、测试和报告等23项 |
| Contract目录 | 无工作树变化 |

这27项中包含Windows Client 1.1.1的主要来源，因此不能把HEAD `673ce7e...`单独当作1.1.1源码身份，也不能直接从当前dirty目录声明clean RC。

### 3.2 Client包与本机状态

| 项目 | 现场结果 |
| --- | --- |
| Client版本 | `1.1.1`，`ChannelAgent.exe version`退出码0 |
| ZIP | `AI-CS-Channel-Agent-1.1.1-windows-x64.zip`，22,129,632 bytes |
| ZIP SHA-256 | `BAF17B07469A8E5FFD274A473BE60412AE22AC04A483D52C8F69A39E48CEB1FA` |
| EXE | `ChannelAgent.exe`，5,632 bytes |
| EXE SHA-256 | `C3D6C0BC3AAD98B93F76B7BDA28AD2B46755E3C1C5C8E3CDBB875503AD996FC9` |
| Authenticode | `NotSigned` |
| 默认安装目录 | `%LOCALAPPDATA%\Programs\AI-CS\ChannelAgent`不存在 |
| 默认数据目录 | `%LOCALAPPDATA%\AI-CS\ChannelAgent`不存在 |
| 运行进程 | 0 |

这些hash可识别当前包，但由于来源dirty且包未签名，只能作为待固化候选证据，不能作为正式客服电脑部署批准。

## 4. 未执行阶段

| 阶段 | 状态 | 原因 |
| --- | --- | --- |
| Phase 2 Clean Candidate Preparation | NOT STARTED | AI-CS SHA Gate已失败；Engine dirty只记录、不清理 |
| Phase 3 Install Customer PC Agent | NOT STARTED | 禁止从未冻结、未签名候选安装 |
| Phase 4 Agent Identity Binding | NOT STARTED | Agent未安装/启动，未请求或显示binding code |
| Phase 5 Runtime Check | NOT STARTED | 无Agent Heartbeat，无Workspace设备在线证据 |
| Phase 6 Human Operation | NOT REQUESTED | 在需要密码/授权前已被基线门禁阻断 |
| Phase 7 PDD Next Gate | RECORDED ONLY | 本轮不接PDD |

## 5. 补救顺序

### 5.1 AI-CS身份对齐

1. 将本报告与治理文档形成最终clean提交，以该提交作为下一轮唯一候选SHA。
2. 使用R027隔离配置的受管stop入口停止8420–8423；不得按端口强杀未知进程。
3. 在同一clean SHA重新构建B/Admin，再用R027配置启动A/B/C/Admin。
4. 核对四条Runtime记录的SHA、source state、fingerprint、工作目录与health完全一致。
5. 只读复核数据库仍为0016、RAG仍为70，不执行迁移或知识同步。

### 5.2 Channel Agent候选冻结

1. 对27项dirty逐项分类，只纳入Channel Agent Foundation、身份/绑定、Windows Client 1.1.1、对应测试与文档；禁止`git add .`。
2. 明确排除PDD Adapter、Gateway Contract语义、真实发送和不属于1.1.1的实验资产。
3. 运行Agent/Engine专项、Contract、安全、Windows安装与打包测试。
4. 从clean commit重新构建ZIP，重新记录版本、commit、ZIP/EXE hash和包清单。
5. 正式客服电脑安装前完成企业代码签名；若只做本机隔离验证，必须取得明确的未签名风险批准并在报告中标注。

### 5.3 重新进入部署Gate

只有以下条件同时成立才允许安装：

- AI-CS工作树clean，当前Git SHA与四个在线Runtime记录一致。
- R027数据库0016和RAG 70只读复核通过。
- Channel Agent来源clean、版本/commit/hash可追溯，Contract目录无未批准变化。
- 安装包签名通过，或有明确的仅限隔离测试批准。

## 6. 人工操作状态

本轮没有要求人工输入密码、扫码、授权或绑定。原因是系统在到达人工步骤前已经因身份门禁停止。

下一轮通过Phase 1后，首次人工停点应出现在“管理员授权并把已注册设备绑定到`ux_kefu`及既有测试店铺”之前；届时必须单独给出操作位置、账号、步骤和“完成后回复继续”，且不得自动输入密码或代替授权。

## 7. PDD前置状态

当前已有：

- R027隔离客服账号、授权店铺、商品/SKU、RAG与Workspace基础。
- Channel Agent 1.1.1候选包及设备身份/心跳设计资产。

当前尚未形成：

- clean且签名的客服电脑Agent安装候选。
- Agent ONLINE、Server Heartbeat和Workspace设备状态的本机部署证据。
- PDD Adapter、Browser Control、Message Listener、Send Executor。

PDD仍保持未连接，消息读取、浏览器控制和真实发送保持关闭。

## 8. 最终判定

Task Gate：`FAIL`

当前状态：`AI_CS_CUSTOMER_PC_DEPLOYMENT_BLOCKED_BASELINE_IDENTITY_MISMATCH`

未达到：`AI_CS_CUSTOMER_PC_DEPLOYMENT_READY`

下一入口：先执行AI-CS同SHA Runtime对齐，再冻结Channel Agent clean candidate；随后重新运行Phase 1，而不是从安装阶段继续。
