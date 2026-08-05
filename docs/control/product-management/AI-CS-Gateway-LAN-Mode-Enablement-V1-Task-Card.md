# AI-CS Gateway LAN Mode Enablement V1 Task Card

| 字段 | 内容 |
| --- | --- |
| 需求 ID | R015 |
| 日期 | 2026-08-05 |
| Owner | AI-CS Production Gateway Network Engineer；A/OPS 主责，C Console 与 shared contracts 受影响复核 |
| 状态 | `DONE` |
| 目标 Gate | `GATEWAY_LAN_MODE_READY` |

## 目标

在不开放 A Core、C API、Admin 和不改变 Gateway Contract V1 的前提下，让 Production Server 同时支持安全默认的 `LOCAL` 与受控 `LAN` Gateway 访问。

## 完成标准

1. `LOCAL` 继续只通过 `127.0.0.1:8000` 访问 Gateway；`LAN` 使用显式 RFC1918 地址、独立端口和允许网段。
2. LAN edge 只转发 `GET /gateway/v1/health` 与 `POST /gateway/v1/decisions`，原始 body/HMAC headers 不重写；`/api/chat` 等所有其他 Core 路径不可达。
3. HMAC、timestamp、nonce、body hash、signature、幂等和 `requires_approval=true` 全部由原 Gateway Core 保持。
4. Windows 启动前对 Private profile、精确 LocalAddress/LocalPort/RemoteAddress 防火墙规则 fail closed；不自动修改或关闭防火墙。
5. start/status/stop 管理 LAN edge；Console 以兼容加法字段展示 `LOCAL/LAN`；Gateway wire 1.0 schema/hash不变。

## 验收证据

- Source commit：`6470a665dfe836573d5c71df95fb6c0fe0815b60`；保护锚点仍为祖先。
- LOCAL：四服务同 SHA/CLEAN；signed Health、Decision、幂等回放、Console `network_mode=LOCAL` 与受管 stop 通过。
- LAN data plane：`192.168.1.11:18080` signed Health/Decision 通过；匿名 Health 401、`/api/chat` 404、幂等回放同 Decision；A/C/Admin 仍为 loopback；Console 显示 `LAN`。
- 防火墙：当前专用规则为 `MISSING`，production wrapper 在启动任何服务前退出 1，未创建规则；read-only check 退出 2。需运维显式配置后再做第二台电脑验收。
- 回归：A `143 passed, 3 skipped`；C `121 passed`；Admin `76 passed` + typecheck/build；OPS `12/12`；contracts `7 passed`；17 schemas valid。

## Gate

`PASS / GATEWAY_LAN_MODE_READY`

该 Gate 表示源码、受控入口、安全 Gate 与本机私网数据面就绪，不表示 Windows 防火墙已由管理员配置、第二台电脑已验收、已部署 TLS/受管 secret，或已连接生产 Channel Engine/PDD。
