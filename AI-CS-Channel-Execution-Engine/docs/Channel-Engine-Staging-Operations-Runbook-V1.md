# Channel Engine Staging Operations Runbook V1

## 1. 适用范围

本 Runbook 仅用于 Channel Engine Staging Foundation。当前 Adapter 为 `OBSERVATION_ONLY` 或 Fake，Execution 使用 Fake Executor；禁止真实 PDD、真实客户、自动发送和生产部署。

配置文件：

- `deploy/staging/runtime-config.json`
- `deploy/staging/deployment-manifest.json`

配置中只能保存 credential reference。credential value、token、password、cookie、private key 不得进入文件、环境 Profile、日志或 Audit。

## 2. 启动

### 2.1 Preflight

1. 确认 `CHANNEL_ENGINE_PROFILE=staging`。
2. 确认 Gateway endpoint 为 HTTPS，不包含用户信息、path、query 或 fragment。
3. 确认 credential provider、credential id、version 和 account ref 仅为引用元数据。
4. 确认 account、conversation 和 action allowlist 非空。
5. 确认 `SEND_MESSAGE`、`AUTOMATIC_REPLY`、`REFUND`、`MODIFY_ORDER`、`PAYMENT` 全部处于 blocked actions。
6. 确认 `CHANNEL_ENGINE_PRODUCTION_ENABLED=false`，且没有生产确认变量。
7. 运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/contract/test_staging_environment_v1.py
```

### 2.2 启动顺序

严格按照 Deployment Manifest：

1. `runtime-store`
2. `control-plane`
3. `ai-cs-gateway-health`
4. `channel-engine-api`
5. `execution-worker`
6. `outbox-publisher`

Foundation 本地验证命令：

```powershell
$env:CHANNEL_ENGINE_PROFILE='staging'
$env:CHANNEL_ENGINE_GATEWAY_ENDPOINT='https://ai-cs.staging.invalid'
$env:CHANNEL_ENGINE_ADAPTER_MODE='OBSERVATION_ONLY'
$env:CHANNEL_ENGINE_CREDENTIAL_PROVIDER='secret-manager'
$env:CHANNEL_ENGINE_CREDENTIAL_ID='channel-engine-staging-pdd-observer'
$env:CHANNEL_ENGINE_CREDENTIAL_VERSION='v1'
$env:CHANNEL_ENGINE_ACCOUNT_REF='staging-synthetic-account'
$env:CHANNEL_ENGINE_POLICY_PROFILE='staging-observation.v1'
$env:CHANNEL_ENGINE_ALLOWED_ACCOUNTS='staging-synthetic-account'
$env:CHANNEL_ENGINE_ALLOWED_CONVERSATIONS='staging-synthetic-conversation-001'
$env:CHANNEL_ENGINE_ALLOWED_ACTIONS='OBSERVE_MESSAGE,REQUEST_DECISION,SIMULATE_SEND_MESSAGE'
.\.venv\Scripts\python.exe -m uvicorn channel_engine.app:app --host 127.0.0.1 --port 18020
```

`.invalid` endpoint是不可路由占位符。Foundation 默认使用本地 Mock AI-CS；上述命令不会连接外部 AI-CS 或 PDD。

### 2.3 启动验收

- `GET /health`：profile=`staging`、adapter mode=`OBSERVATION_ONLY`、production=false、automatic send=false。
- `GET /control/v1/status`：Kill Switch 状态和 active config 可读取。
- `GET /control/v1/health`：Runtime Store、Gateway、Adapter、Worker、Outbox、Policy 状态可聚合。
- 非 allowlist conversation 请求返回 HTTP 403，且不进入 AI-CS Decision 流程。

## 3. 停止

正常停止顺序必须与启动顺序相反：

1. 停止 Outbox Publisher 新领取。
2. 停止 Execution Worker 新领取。
3. 等待当前 RUNNING Execution 按安全策略完成；无法确认的任务由 lease recovery 转为 UNKNOWN。
4. 停止 API。
5. 停止 Gateway health probe。
6. 停止 Control Plane。
7. 最后停止 Runtime Store。

不得删除 Receipt、Event、Audit 或 Config Snapshot。

## 4. Kill Switch

### 4.1 启用条件

- 发现 allowlist 漂移。
- Adapter health 异常。
- Gateway schema mismatch 或认证异常。
- UNKNOWN 异常增长。
- Outbox 重复投递或 backlog 超阈值。
- 无法确认运行时配置版本。

### 4.2 操作

通过受信任的内部运维入口调用 `ControlPlaneService.enable_kill_switch`，必须提交 operator 和大写 reason code。V1 不暴露未认证的 Kill Switch 写 HTTP API。

启用后确认：

- 新 Approval 不能创建 Execution。
- PENDING Execution 不能被领取。
- RUNNING Execution 仅按安全策略结束。
- Receipt、Event 和 Audit 历史保持不变。

解除前必须完成根因定位、config snapshot 核对和 UNKNOWN reconciliation，再通过受信任入口调用 `disable_kill_switch`。

## 5. 故障与恢复

| 故障 | 立即动作 | 恢复条件 |
| --- | --- | --- |
| Runtime Store 不可用 | 启用 Kill Switch，停止 Worker/Publisher | Store 可读写、版本清单为 1.0、完整性检查通过 |
| AI-CS timeout/degraded | 停止新 Decision，禁止执行 | `/gateway/v1/health` 和 Contract V1 校验通过 |
| Invalid signature | 保持 Kill Switch，检查 key reference/version | 认证恢复且 Audit 无 secret |
| Worker crash | 等待 lease 过期并执行 Recovery | RUNNING 转 UNKNOWN，Receipt/Event 已追加 |
| UNKNOWN | 禁止自动重发 | 人工 reconciliation 完成 |
| Outbox backlog | 保持稳定 publish key，检查 Publisher | 过期 PROCESSING 已接管，backlog 下降 |
| Adapter disconnected | 禁止 ingestion/action | Health 恢复且 account/conversation scope 复核 |
| Allowlist denial | 不扩大 allowlist应急绕过 | 新 Config Snapshot 经人工审核并激活 |

## 6. Config Rollback

1. 启用 Kill Switch。
2. 从 Audit Timeline 确认最后一个已知安全的 Config Snapshot ID。
3. 核对 adapter config version、policy version、gateway version。
4. 通过受信任入口调用 `rollback_config_snapshot`，填写 operator 和 reason。
5. 确认 active snapshot 已切换，Audit action 为 `CONFIG_SNAPSHOT_ROLLED_BACK`。
6. 重新执行 Health 和 allowlist smoke test。
7. 完成人工批准后才解除 Kill Switch。

Rollback 不覆盖或删除旧 Snapshot。数据库 schema 使用 forward migration；不得用文件覆盖或 destructive reset 回滚运行时数据库。

## 7. Escalation Evidence

故障记录仅保存：

- profile/config/snapshot version
- execution/receipt/event id
-状态与时间线
- operator、reason code
- component health 和指标

禁止附加 credential value、token、cookie、客户消息正文或真实客户标识。
