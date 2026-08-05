# 《AI-CS Gateway LAN Mode Enablement Report V1》

日期：2026-08-05

需求：R015

分支：`release/product-reliability-hardening-v1`

实现提交：`6470a665dfe836573d5c71df95fb6c0fe0815b60`

保护锚点：`0b3367f85999f1dc840accf23742c290eb53746b`（仍为祖先）

Final Status：`GATEWAY_LAN_MODE_READY`

## 1. 网络模式设计

### 1.1 拓扑

| 模式 | Gateway 入口 | A Core | C API / Admin | 行为 |
| --- | --- | --- | --- | --- |
| LOCAL（默认） | `http://127.0.0.1:8000/gateway/v1/*` | `127.0.0.1:8000` | `127.0.0.1:8011 / 5174` | 不启动 LAN edge，不需要 Gateway LAN 防火墙规则 |
| LAN | `http://<private-ip>:18080/gateway/v1/*` | 仍为 `127.0.0.1:8000` | 仍为 `127.0.0.1:8011 / 5174` | 新增独立、最小、受管 Gateway LAN edge |

不能把现有 A FastAPI 直接绑定 LAN：那会同时暴露 `/api/chat`、管理投影、docs 和其他 A 路由。新 edge 只允许冻结的 Health 与 Decision 两条路径；`/api/chat`、`/api/*`、OpenAPI、root 和未批准 Gateway 路径不转发。

LAN edge 按原始字节转发 body，只转发 Contract V1 所需 header；响应只保留 Contract header。它关闭 OpenAPI、redirect slash 和 access log，拒绝 query、重复 contract header、非允许来源和上游非 loopback 地址。

## 2. 配置方式

版本化示例位于 `scripts/windows/config.local.ps1.example`。正式 ignored config 可覆盖：

| 配置 | 默认 | 约束 |
| --- | --- | --- |
| `GatewayLanBindAddress` | `auto` | `auto` 或当前物理网卡的 RFC1918 IPv4；拒绝 `0.0.0.0`、loopback、公网、VPN/虚拟网卡 |
| `GatewayLanPort` | `18080` | 1–65535，必须与 5173/5174/8000/8011 不同 |
| `GatewayAllowedNetworks` | `@('auto')` | 自动解析当前物理子网，或填写位于该子网内的规范 RFC1918 CIDR；禁止 `Any` 和跨子网放宽 |
| `GatewayUpstreamTimeoutSeconds` | `180` | 正整数；LAN edge 上游固定为 `127.0.0.1:<RagPort>` |

当前机器只读解析结果为：物理以太网 `192.168.1.11/24`、Windows `Private` profile、Gateway endpoint `192.168.1.11:18080`、allowed network `192.168.1.0/24`。VPN/198.18 地址未被选择。

Server 网络模式仍由统一入口的 `-Mode Local`、`-Mode Lan` 或受管 `Auto` 偏好决定；没有新增明文 secret 配置。A 进程通过 `AI_CS_SERVER_NETWORK_MODE` 只接收 `LOCAL/LAN` 状态事实，Console response 不包含 IP、CIDR、secret、路径或凭据。

## 3. 安全边界

- Gateway HMAC-SHA256、timestamp skew、nonce replay prevention、raw-body SHA-256、signature、request identity 和 durable idempotency 均在原 Core 内验证；LAN edge 无匿名旁路。
- socket source IP 必须属于 allowed CIDR；`X-Forwarded-For` 不参与信任判断。
- 所有 Decision 仍固定 `requires_approval=true`；LAN mode 不增加执行、Receipt/Event、PDD/Chrome/Browser 能力。
- A Core、C API、Operations Console 继续 loopback；LAN edge 实测 `/api/chat` 返回 404。
- Gateway Contract V1 schema 未修改；canonical SHA-256 保持 `e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`。
- 共享 contracts 仅从 0.7.0 加法升级至 0.8.0：Console schema 新增可选 `server.network_mode`，缺失时 C consumer 默认 `LOCAL`。这不是 Gateway wire 变更。

### Windows Firewall

只读检查：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/windows/check_ai_cs_gateway_firewall.ps1
```

LAN production start 要求恰好一条 Enabled/Inbound/Allow/Private/TCP 规则，并精确匹配 bind IP、18080 和 allowed CIDR。规则缺失、重复、`Any`、Public、错误端口或网段都会 fail closed。

仓库提供管理员显式工具 `configure_ai_cs_gateway_firewall.ps1`；它显示完整范围并要求人工输入 `CONFIGURE`，不会自动运行、不会关闭防火墙，也不会开放 8000、8011 或 5174。受管环境也可由企业策略创建等价规则。

## 4. 启动与状态

LOCAL：

```powershell
scripts\windows\start_ai_cs_server.bat -Mode Local -NoBrowser
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/windows/status_ai_cs_server.ps1 -Mode Local
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/windows/stop_ai_cs_server.ps1
```

LAN（管理员或企业策略先配置并复核防火墙）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/windows/check_ai_cs_gateway_firewall.ps1
scripts\windows\start_ai_cs_server.bat -Mode Lan -NoBrowser
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/windows/status_ai_cs_server.ps1 -Mode Lan
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/windows/stop_ai_cs_server.ps1
```

start 在 Core 生命周期前执行网络和防火墙 Gate；LAN edge 启动失败会清理自己的受管进程。status 显示 network mode、edge listener、allowed network、firewall state、Gateway version 与 Contract version。stop 先停止经过 PID/命令/监听身份验证的 `gateway-lan`，再停止原四服务；不按端口强杀未知进程。

Operations Console 的系统状态页新增“Gateway 网络模式”，旧 0.7.0 response 缺字段时显示 `LOCAL`。R006/R009 页面、C Backend 和数据库均未改变。

## 5. 测试结果

| Gate | 结果 |
| --- | --- |
| A 全量 | `143 passed, 3 skipped`；3 项仍是需显式环境的真实 E2E |
| LAN edge / Gateway / Runtime 专项 | `27 passed`；含 raw HMAC 转发、ACL、路由隔离、真实 Core auth、Decision 与幂等 |
| C 全量 | `121 passed`；隔离测试数据库 |
| Admin | `29 files / 76 tests passed`；typecheck、production build PASS |
| Windows OPS | `12/12` scripts PASS；含新增 LAN/firewall/wrapper tests |
| Shared contracts | `7 passed`；17 JSON schemas valid |
| Contract freeze | Gateway V1 canonical SHA 与冻结值一致 |

真实 clean-SHA 验证：

- LOCAL：C/A/B/Admin 均在 `6470a665dfe8`、`CLEAN`、`standard/LOCAL` 运行；signed Health `HEALTHY/1.0`；Decision HTTP 200、`NO_ACTION`、`requires_approval=true`，重复请求返回同 Decision 且 `Idempotency-Replayed=true`；Console 为 `READY/HEALTHY/LOCAL/1.0`。
- LAN data plane：Core 以 `standard/LAN` 运行；测试 edge 实际监听 `192.168.1.11:18080`。signed Health `HEALTHY/1.0`，匿名 Health 401，Decision 200、Contract 1.0、人工审批 true、幂等回放同 Decision，`/api/chat` 404；A 8000、C 8011、Admin 5174 均保持 `127.0.0.1`；Console 为 `LAN`。
- 防火墙 Gate：本机专用规则当前 `MISSING`；production LAN wrapper 在启动前退出 1，五个相关端口均未监听，规则数量仍为 0。read-only checker 按约定退出 2。
- 收尾：测试 edge 和四服务均已停止，5173/5174/8000/8011/18080 全部释放；Auto 网络偏好已恢复为安全默认 `LOCAL`；实现提交验证时 Git clean。

本机私网地址测试证明 listener、ACL、转发、HMAC 与 contract data plane；它不是独立客服电脑跨主机证明。第二台电脑必须在专用防火墙规则配置后另做 signed Health/Decision 验收。

## 6. 风险与后续

1. 当前网络仍是 HTTP。HMAC 提供请求完整性与调用方认证，但不提供传输机密性；含客户内容的 LAN 使用仍需受控 Private 网段，跨不可信网络前必须加 TLS/受管 ingress。
2. 本机尚无专用 18080 防火墙规则，因此完整 production wrapper LAN start 按设计被阻止。管理员配置精确规则并用第二台电脑验证前，不得宣称 Windows 部署已完成。
3. secret manager、rotation、速率限制、集中审计/告警和多实例共享幂等仍是后续部署 Gate；不得把 ignored secret file 当作最终密钥治理。
4. 物理网卡 IP/子网变化会使旧规则失配并阻止启动；这是安全行为。运维需重新检查并显式更新规则，不能改成 `Any`。
5. 回滚：先运行 `stop_ai_cs_server.ps1`，再以 `-Mode Local` 启动。无需数据库迁移、RAG 重建、知识重发或 B/C 回滚。防火墙规则的删除/变更由管理员或企业策略单独执行。

## Final Status

`GATEWAY_LAN_MODE_READY`
