# ChannelAgent 2.0.0rc4 Observation Foundation Checkpoint

日期：2026-08-11

状态：`RC4_OBSERVATION_FOUNDATION_CHECKPOINT`

离线最高 Gate：`RC4_OFFLINE_OBSERVATION_READY`

## 收口结论

本 checkpoint 把上个开发窗口留下的观察链骨架收敛成一个可测试、可打包、默认关闭且不依赖真实拼多多的安全基线。它不是“真实 PDD 已就绪”声明，也不包含受控发送。

- Channel Engine 源码版本：`0.2.0rc2`
- Channel Agent / Windows / Brand：`2.0.0rc4`
- Agent Control：`2.1`（未变）
- Gateway wire：`1.0`（未变）
- 默认 `message_observation_enabled=false`、`observation_stage=DISABLED`
- `OFFLINE_REPLAY` 在配置层禁止浏览器、PDD 登录观察、PDD URL、生产运行模式和真实发送
- Live/Replay 都通过 `PDDPageReadPort` 后进入同一个 conversation/message 解析与边界校验
- Replay 夹具是 `pdd-readonly-page-fixture.v1` 合成页面抽取结果，不是预制 `CustomerContext`
- Agent 观察阶段固定为：`DISABLED → CONVERSATION_LIST → MESSAGE_CAPTURE → HOST_INGEST → ASSISTANT_FEED → AI_SUGGESTIONS`
- Host ACK 前本地游标不前移；未 ACK 数据可恢复，Edge 明文业务载荷最长保留 30 分钟
- Host observation 最长保留 24 小时；assistant snapshot 最长保留 30 分钟；过期项可确定性清理
- Host Worker 生产组合可用环境变量显式启用 `HOST_INGEST`；更高阶段必须注入本地 assistant runtime，否则启动失败关闭
- AI suggestion 只产生 `WAITING_APPROVAL` / `MANUAL_INTERVENTION` 快照，安全事实固定为 execution/send/receipt/browser-write 全部 0
- 新增签名、设备范围限定的 `GET /channel-agent/v2/assistant-snapshot`
- Agent 只在内存缓存完整快照，本地 SQLite event journal 继续只保存状态与标识符
- 本地 `/local-api/v1/events` 提供 SSE，前端同时保留 1.5 秒降级轮询

## 能力边界

| 能力 | 无真实 PDD 可完成 | 本 checkpoint | 仍需真实 PDD / 外部条件 |
| --- | --- | --- | --- |
| 配置、身份、Store scope、安全默认值 | 是 | 已完成 | 生产凭据与部署验收 |
| 脱敏页面夹具、Replay 端口、同一解析器 | 是 | 已完成 | 无 |
| 会话列表、消息捕获、100 条边界压力 | 是 | 已完成 | 真实 DOM selector 证据 |
| Persist-before-ACK、重启恢复、30 分钟 Edge 留存 | 是 | 已完成 | LAN 抖动现场长稳 |
| Host inbox、Worker、4 秒消息组、AI suggestion | 是 | 已完成 | 正式本地 AI-CS gateway 配置与现场长稳 |
| 签名 snapshot、Agent feed、SSE、前端即时刷新 | 是 | 已完成 | 双机 LAN 与浏览器人工验收 |
| AI-CS 内部 Store ↔ PDD platform_store_id 精确映射 | 是 | 已完成（源码） | 正式数据库受控迁移 0017/0018 |
| 真实 PDD 页面识别、selector/fingerprint 证据 | 否 | 未声明完成 | 人工授权的只读现场 Gate |
| 真实消息持续观察 | 否 | 未声明完成 | 真实页面、账号、网络与长稳 Gate |
| 自动点击非当前会话 | 否 | 明确禁止 | 不在观察基线范围 |
| 受控发送 / 自动回复 | 否 | 不在范围；固定关闭 | 独立安全版本和激活 Gate |

## 真实环境保护声明

本轮没有安装或升级当前运行中的 RC3，没有关闭现有 Edge，没有读取其 Profile、Cookie、Token 或页面内容，也没有从 Agent/开发代码发起 PDD 请求。因此只能声明“本轮 Agent/开发代码产生的 PDD 请求为 0”；在 Edge 保持打开的前提下，不能把整台机器的后台网络活动表述为 0。

## 验证记录

- Channel Engine：`709 passed / 1 skipped`；skip 为必须显式授权的隔离 Edge smoke，不属于离线 Gate。
- AI-CS Platform Backend：`173 passed`。
- AI-CS Customer Frontend：typecheck PASS；`44 files / 205 tests passed`；production build 与 channel-agent build PASS。
- Agent composition：`validated_files=28`，合成脱敏 fixture Gate PASS。
- RC4 pyz：30 个成员；`execution_control.py`、`edge_execution.py`、`pdd_workspace_send.py` 均不存在。
- 隔离归档：`AI-CS-Channel-Agent-2.0.0rc4-windows-x64.zip`。
- 归档 SHA-256：`e4f28449c0df532b43067008d2c1575b5b12581b1c32672a312a8fdfb593c3f0`。
- 当前 RC3 `release-manifest.json` 与 `channel-agent.pyz` 打包前后 SHA-256 均保持不变。

## 未关闭 Gate

1. 真实 PDD selector evidence、page fingerprint 与只读现场观察。
2. 第二台客服电脑、TLS/LAN、防火墙和断网恢复长稳。
3. 正式 AI-CS 数据库从当前运行版本受控升级到 0018。
4. 企业代码签名与 Windows 受管服务化。
5. 受控发送必须另开版本；RC4 不得通过本地配置启用。
