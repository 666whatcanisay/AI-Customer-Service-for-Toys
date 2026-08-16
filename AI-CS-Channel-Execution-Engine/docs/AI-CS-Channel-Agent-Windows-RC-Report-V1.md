# AI-CS Channel Agent Windows RC Report V1

## 技术摘要

AI-CS Channel Engine 已形成可复制到 Windows 客服电脑运行的 `AI-CS-Agent 1.0.0-rc.1`。本次新增了独立的 production-only `ai_cs_agent` 组合根、统一 `configure/start/status/stop` 入口、严格配置域、Windows Credential Manager 引用边界、冻结 Gateway Contract V1 HMAC Client、Chrome 与独立 Profile 检测、Session 恢复、审批/Lease/Kill Switch 执行边界、追加式 Receipt 和结构化事件日志。

最终 ZIP 包内置 CPython 3.12 标准运行时，不依赖系统 Python；应用 zip 中只有 `ai_cs_agent` 和启动入口，未包含 `channel_engine` 混合 barrel、Fake、Sandbox、Discovery、PDD、Pilot 或 Mock Server。包没有真实渠道实现，因此不能登录 PDD、读取客户消息或发送消息。

Windows RC 专项测试为 `10 passed`。除既有外部受控 AI-CS E2E 模块外，仓库回归为 `394 passed`。完整套件为 `394 passed + 6 setup errors`；6 个错误共享同一 sibling AI-CS Gateway health 夹具，发生在当前 dirty AI-CS 工作区，按边界未修改 AI-CS、未放宽 Gateway Contract，也未以 Mock 替代。

## 关键结果与证据

| 检查项 | 结果 | 证据 |
|---|---:|---|
| 保护锚点 | PASS | `HEAD=b2c64d54987f1f066a02de8e9e667d5cc0f9857c` |
| 生产组件 | 8 | Runtime、Session、Browser、Adapter、Gateway、Execution、Receipt、Observability |
| 应用 zip entries | 16 | root 仅 `__main__.py`、`ai_cs_agent/` |
| 实验应用路径 | 0 | PDD/Fake/Sandbox/Discovery/Mock/Pilot 扫描为空 |
| Python runtime | PASS | 内置 CPython 3.12；`site-packages=false` |
| Windows 批处理 status | PASS | 初始 `Agent=INIT`、`Kill Switch=ENABLED` |
| Windows RC tests | 10/10 | `tests/windows_agent/` |
| 非外部回归 | 394/394 | 排除 sibling AI-CS controlled E2E 模块 |
| 完整回归 | PARTIAL | 394 passed；外部 health 夹具 6 errors |

机器可读证据：`evidence/AI-CS-Agent-Windows-RC-V1-validation.json`。发布清单：`dist/windows-rc/AI-CS-Agent/release-manifest.json`。

## 作用域、定义与判断口径

- **Windows RC Ready**：发布目录可在 Windows x64 上由自带 CPython 3.12 运行；`configure/start/status/stop` 可用；配置和运行状态 fail-closed；不代表真实渠道或生产 AI-CS 已联调。
- **Production-only application**：应用 zip 的 import graph 不依赖现有混合 `channel_engine` package；测试和平台实验不会进入 application zip。
- **Secret-free config**：配置只保存 `wincred://` 引用，不保存 Cookie、Token、Password、HMAC secret 或 Authorization header。
- **Ready**：AI-CS 签名 health 通过、客服身份存在、Chrome 可用、独立 Profile 已初始化；浏览器登录状态仍为 `AUTH_REQUIRED`。
- **执行能力**：RC 只含 Decision/Approval/Execution/Lease/Kill Switch 授权边界和 Receipt Ledger，不含平台发送实现。

本报告以 2026-08-05 本地 workspace、最终构建清单、专项测试输出和仓库回归输出为证据。没有连接真实 PDD、真实客户、生产 AI-CS 或真实浏览器会话。

## Agent 架构已从混合 Engine 入口中隔离

```text
start_ai_cs_agent.bat
        |
        v
  ai-cs-agent.pyz ------------------- production application only
        |
        +-- Config + Windows Credential Reference
        +-- Agent Runtime + durable local state
        +-- Gateway V1 HMAC health/decision client
        +-- Chrome detector + dedicated profile manager
        +-- Channel Session recovery
        +-- Adapter Protocol (no platform implementation)
        +-- Approval/Lease/Kill Switch execution boundary
        +-- append-only Receipt ledger
        +-- structured lifecycle event log

Excluded: channel_engine barrels, Fake, Sandbox, Discovery, PDD, Pilot,
          Mock Server, platform send implementation, AI/RAG/Knowledge.
```

`src/ai_cs_agent/` 不 import `channel_engine`，因此现有 `channel_engine.app`、package `__init__.py` 和自动 package discovery 中的实验组合不会被运行时加载。显式组合清单位于 `packaging/windows-agent/production-composition.json`，构建脚本逐项复制 allowlist，随后执行禁止 import 扫描。

Gateway Client 使用冻结路径 `/gateway/v1/health` 和 `/gateway/v1/decisions`，HMAC canonical string、Contract header、最多 3 次传输尝试、Error Envelope、`requires_approval=true` 以及 UNKNOWN fail-closed 规则保持不变。RC 不提供生成 AI 回复的逻辑。

## 打包结构可直接复制到 Windows 节点

```text
AI-CS-Agent/
├── exe/
│   ├── ai-cs-agent.pyz
│   ├── python.exe
│   ├── python312.dll
│   ├── python3.dll
│   └── python312._pth
├── config/
│   └── agent.example.json
├── runtime/
│   ├── contracts/ai-cs-channel-engine-gateway-contract-v1.schema.json
│   └── python/                 # CPython standard library only
├── logs/
├── scripts/
│   └── start_ai_cs_agent.bat
└── release-manifest.json
```

- 解压目录：`dist/windows-rc/AI-CS-Agent/`
- 交付 ZIP：`dist/windows-rc/AI-CS-Agent-1.0.0-rc.1-windows-x64.zip`
- ZIP SHA-256：`41cfa76a1ad9d8f963353692806433fe607c24babea65256f2281afe0250f031`
- ZIP 大小：17,144,127 bytes
- 解压文件：1,047；总大小 45,803,096 bytes
- Gateway Schema SHA-256：`fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`

CPython 标准库被放入 `runtime/python`，第三方 `site-packages` 被明确删除。`python312._pth` 将解释器限制到包内标准库与 application zip，用户级 site packages 由启动脚本关闭。构建脚本保留 Python 许可证并为发布文件生成 SHA-256。

## 启动与首次配置不接触 Secret

在解压后的目录运行：

```bat
scripts\start_ai_cs_agent.bat configure
scripts\start_ai_cs_agent.bat start
scripts\start_ai_cs_agent.bat status
scripts\start_ai_cs_agent.bat stop
scripts\start_ai_cs_agent.bat kill-switch enable
```

如果 `start` 时没有 `config/agent.json`，入口先进入交互式安全配置，只询问：

- AI-CS Server origin；
- Agent ID、Device ID；
- 客服身份；
- `STAGING` 或 `PILOT` runtime mode；
- Gateway Client/Key ID；
- `wincred://` credential reference。

配置过程不询问明文 credential。实际 HMAC material 仅在签名时从 Windows Credential Manager 解析到内存；`repr`、状态文件、事件日志和错误消息均不输出 material。

首次启动状态顺序：

```text
FIRST_START
  -> CHECKING_ENVIRONMENT
  -> CONNECTING_SERVER
  -> CONFIGURING_IDENTITY
  -> CHECKING_BROWSER
  -> INITIALIZING_PROFILE
  -> READY
  -> RUNNING
```

任一步失败进入 `FAILED`，状态 API/CLI 只给操作员可理解的提示，不输出技术堆栈或 secret。Server 不可达时不会继续初始化 Browser；Chrome 不可用时不会宣称 Ready。

## 配置规则默认拒绝不安全输入

`agent.json` 的固定域包括：

| 配置域 | 字段 | 关键约束 |
|---|---|---|
| agent | agent_id、device_id、customer_service_identity、runtime_mode | ID 必须符合 Contract identifier；RC 只允许 STAGING/PILOT |
| server | address、client_id、key_id、credential_reference、timeout_seconds | origin 禁止内嵌凭据、query、fragment；远程 PILOT 强制 HTTPS |
| browser | chrome_path、profile_directory | Profile 必须位于 Agent home 且不得位于用户默认 Chrome Profile |
| safety | kill_switch、manual_approval、auto_reply | RC 强制 manual_approval=true、auto_reply=false |

未知 root/section 字段、明文敏感字段、非 `wincred://` 引用、Production mode、无人工审批或自动回复配置均拒绝启动。Kill Switch 默认开启，并在本地 durable state 中持久化。

## Browser 与 Session 保持只读准备状态

Browser Manager 只执行：

- 检测显式或标准安装位置的 `chrome.exe`；
- 校验独立 Profile 不属于用户默认 Chrome `User Data`；
- 在 Agent home 下初始化专用 Profile marker；
- 返回 Chrome/Profile/Process/Session 状态。

它不会启动 PDD 页面、不会自动登录、不会导出 Cookie、不会读取消息，也没有点击/输入/发送方法。Session 从历史 `CONNECTED/DEGRADED/EXPIRED` 恢复时强制降为 `AUTH_REQUIRED` 并要求重新验证登录，防止重启后错误继承认证状态。

## Execution、Receipt 与 Observability 均为 fail-closed

Execution Boundary 只有在以下条件同时满足时才授权后续 adapter：

1. Kill Switch 关闭；
2. Decision 为 `APPROVED`；
3. Human Approval 为 `APPROVED`；
4. Execution 为 `RUNNING`；
5. worker owner、lease token 和 lease expiry 有效。

RC 没有任何生产 Channel Adapter 实现，因此授权通过也不会产生真实平台动作。Receipt Ledger 是追加式 JSONL：同一 execution 的相同 Receipt 返回原记录，不同 Receipt 冲突被拒绝。`UNKNOWN` 强制 `reconciliation_required=true` 且 `automatic_retry_allowed=false`。

Observability 只记录 Agent/Gateway/Browser/Session/Kill Switch 生命周期类别；递归拒绝 Cookie、Token、Password、Secret、Authorization、客户消息正文和 payload 字段。Chrome 绝对路径在 durable status 中被移除。

## 测试覆盖了 RC 的安全路径

### Windows RC 专项

命令：`python -m pytest tests/windows_agent -q`

结果：`10 passed`。

覆盖：

- 严格配置与 credential reference；
- 独立 Chrome Profile；
- Runtime start/status/stop；
- 配置错误；
- Server 不可达；
- Session restart recovery；
- Kill Switch 持久化与执行阻断；
- 未审批执行阻断；
- UNKNOWN Receipt 无自动重试；
- 冻结 HMAC signed health；
- production import graph 与敏感值扫描。

### 仓库回归

| 范围 | 结果 | 解释 |
|---|---|---|
| 排除 external controlled AI-CS E2E | 394 passed，1 warning | Channel Engine 本地与本次 RC 回归全绿 |
| 完整套件 | 394 passed，6 errors，1 warning | 6 errors 共享同一 sibling AI-CS Gateway health setup |

完整回归的 6 个 setup error 返回 `GatewayContractViolation`。只读审计确认 sibling `AI-CS` workspace 当前有未提交的 Gateway Server 变更；按任务边界未修改该工程、未改变冻结 Contract、未接生产服务。该问题是发布前跨仓集成阻断，不影响本包专项 gate，但必须在真实 AI-CS RC 对齐后重新执行完整套件。

唯一 warning 是现有 Starlette TestClient/httpx 弃用提示，与本次 runtime package 无依赖关系。

## 限制、风险与稳健性判断

1. **真实 AI-CS 联调未完成。** RC Client 已通过本地签名 contract test，但 sibling AI-CS 当前 health fixture 漂移；上线前必须由 AI-CS RC 提供一致的签名 health 响应并重跑 6 个 E2E。
2. **没有真实 Channel Adapter。** 这是刻意安全边界；当前包不能接 PDD、读取客户消息或发送回复。
3. **没有 Windows Service/Installer。** 当前交付是 portable ZIP + batch；进程由用户会话启动，不包含 MSI、服务账户、自动升级或签名安装器。
4. **Windows Credential 只读。** RC 能读取预置 Generic Credential，但不负责创建、轮换或删除凭据；这些应由部署系统或受控运维流程承担。
5. **本地状态为单节点文件。** JSON/JSONL 使用原子替换或 flush/fsync，但尚未提供多进程文件锁、集中日志或远程运维鉴权。
6. **Browser 仅准备。** Chrome 检测未启动真实页面，也未验证特定 Chrome 版本兼容、登录态或 Selector。
7. **制品未代码签名。** ZIP 和文件有 SHA-256，但 `python.exe`、batch 和 ZIP 尚未经过企业 Authenticode 签名流程。

这些限制意味着该制品适合作为 Windows 节点 RC、安装/启动/配置/安全边界验证，不是生产渠道上线包。

## 建议的下一阶段

1. 冻结 AI-CS Server RC 并修复跨仓 signed health compatibility，重跑完整 400-test 目标套件。
2. 为 Windows Credential provision/rotation 建立独立运维 Runbook，不让 Agent 接收明文 secret。
3. 增加 MSI 或企业软件分发封装、Windows Service host、日志轮转与 Authenticode 签名。
4. 在独立授权任务中接入一个经过审计的 Channel Adapter；仍保持 Kill Switch 默认开启和 manual approval 必选。
5. 增加干净 Windows VM 安装矩阵、Chrome 版本矩阵、重启恢复和杀进程恢复测试。

## 仍需确认的问题

- AI-CS Server RC 的 build/version 与本次冻结 Gateway Schema 如何做双向发布绑定？
- Windows Credential 的创建、ACL、轮换和吊销由哪一套企业运维系统负责？
- RC 后续采用 Windows Service、计划任务还是托盘应用作为正式宿主？
- 制品签名证书、发布渠道和回滚保留策略由谁审批？

---

Final Status: `CHANNEL_AGENT_WINDOWS_RC_READY`
