# 《Channel Engine Staging Environment Foundation V1》

## 1. 结论

Channel Engine 已建立统一、版本化、默认安全的 Environment Profile V1，并完成 Staging runtime config、deployment manifest、scope safety guard 和 operations runbook。

本阶段没有连接真实 PDD、没有使用真实客户数据、没有自动发送、没有部署 Production、没有修改 AI-CS。

最终状态：`CHANNEL_ENGINE_STAGING_READY`

## 2. Environment Profiles

Profile 版本冻结为 `1.0`。

| Profile | 默认状态 | Gateway | Adapter | Credential | 执行边界 |
| --- | --- | --- | --- | --- | --- |
| Mock | 默认 | loopback HTTP(S) | `FAKE` | 禁止 | Human Approval + Fake Executor |
| Staging | 显式选择 | HTTPS metadata | `FAKE` / `OBSERVATION_ONLY` | reference only | account + conversation + action allowlist |
| Production | 默认拒绝 | HTTPS metadata | `PRODUCTION_PREPARATION` | reference only | enable flag + confirmation phrase + allowlist |

当 `CHANNEL_ENGINE_PROFILE` 未设置时，系统选择 Mock。Production 只有同时满足以下条件才可构造配置：

- `CHANNEL_ENGINE_PRODUCTION_ENABLED=true`
- `CHANNEL_ENGINE_PRODUCTION_CONFIRMATION=ENABLE_CHANNEL_ENGINE_PRODUCTION`
- Adapter mode 为 `PRODUCTION_PREPARATION`
- HTTPS Gateway、credential reference、allowlist 均有效

即使显式构造 Production Preparation Profile，V1 的 `automatic_send_enabled` 仍固定为 false。本 Sprint 没有执行生产部署。

## 3. Staging Configuration

Staging 配置字段：

- `gateway_endpoint`
- `adapter_mode`
- `credential_reference.provider`
- `credential_reference.credential_id`
- `credential_reference.version`
- `credential_reference.account_ref`
- `policy_profile`
- `allowlist.account_refs`
- `allowlist.conversation_ids`
- `allowlist.allowed_actions`
- `allowlist.blocked_actions`

配置采用 Pydantic strict/frozen/extra-forbid 模型。Gateway 禁止 URL credential、path、query、fragment。Staging/Production 只接受 HTTPS。

Credential 模型没有 secret value 字段。环境加载器拒绝 `SECRET`、`TOKEN`、`PASSWORD`、`COOKIE`、`PRIVATE_KEY` 类配置键；Manifest 测试递归检查所有 key。

参考文件：[runtime-config.json](../deploy/staging/runtime-config.json)。

## 4. Staging Safety Guard

Staging 操作必须同时满足：

```text
account_ref in account allowlist
AND conversation_id in conversation allowlist
AND action in action allowlist
AND action not in blocked actions
```

强制 blocked actions：

- `SEND_MESSAGE`
- `AUTOMATIC_REPLY`
- `REFUND`
- `MODIFY_ORDER`
- `PAYMENT`

V1 允许的安全 action 仅为：

- `OBSERVE_MESSAGE`
- `REQUEST_DECISION`
- `SIMULATE_SEND_MESSAGE`

`SIMULATE_SEND_MESSAGE` 必须经过 Decision、Human Approval、Execution Worker，且最终只调用 Fake Executor，不调用渠道 send_message。

应用入口在创建 Conversation/Decision 前检查 OBSERVE 和 REQUEST_DECISION；人工 Approval 创建 Fake Execution 前检查 SIMULATE_SEND_MESSAGE。拒绝返回 HTTP 403，不产生绕过执行。

## 5. Deployment Manifest

[deployment-manifest.json](../deploy/staging/deployment-manifest.json) 定义：

- Runtime Store、AI-CS Gateway、Credential Provider 三类依赖引用。
- `/health` liveness。
- `/control/v1/health` aggregate readiness。
- `/control/v1/status` control status。
- Runtime Store → Control Plane → Gateway Health → API → Worker → Outbox Publisher 启动顺序。
- 完全相反的安全停止顺序。
- Production deployment、real channel、automatic send 均为 false。

Manifest 只描述部署依赖，没有执行部署，也没有保存可用 secret。

## 6. Health 与运行时快照

`GET /health` 增加：

- `environment`
- `environment_profile_version`
- `adapter_mode`
- `production_enabled`
- `automatic_send_enabled`

Control Plane Health 继续聚合 Gateway、Adapter、Worker、Outbox、Policy、Kill Switch、Config Snapshot 和 Runtime Metrics。

## 7. Operations

运维 Runbook 覆盖：

- Preflight 与启动顺序
- 正常停止
- Kill Switch 启用与解除
- Store、Gateway、Worker、Outbox、Adapter 故障
- UNKNOWN reconciliation
- Config Snapshot rollback
- 安全 Evidence 收集

详见：[Channel Engine Staging Operations Runbook V1](Channel-Engine-Staging-Operations-Runbook-V1.md)。

## 8. 测试

新增测试覆盖：

- Profile 默认 Mock 和环境隔离。
- Production 默认拒绝与双重显式授权。
- Staging HTTPS、credential reference、policy、allowlist 校验。
- account/conversation/action 三重门禁。
- refund、order modification、payment、real send 强制阻断。
- 配置 extra field 和敏感环境键拒绝。
- Runtime config 和 Deployment Manifest schema validation。
- 启停顺序与 health endpoint 校验。
- Staging API allowlist 拒绝及人工批准 Fake Execution。

验证结果：

```text
Staging/Profile targeted tests: 9 passed
Full regression suite:          173 passed
compileall / pip check:          passed
```

完整回归仅有一条既存 Starlette TestClient/httpx 弃用提示，不影响环境隔离和安全门禁。

## 9. Quality Gates

| Gate | 结果 |
| --- | --- |
| Mock/Staging/Production Profile | PASS |
| Production default deny | PASS |
| Staging scope guard | PASS |
| Secret-reference-only config | PASS |
| Deployment manifest | PASS |
| Operations runbook | PASS |
| Forbidden boundary | PASS |

Final Status: `CHANNEL_ENGINE_STAGING_READY`
