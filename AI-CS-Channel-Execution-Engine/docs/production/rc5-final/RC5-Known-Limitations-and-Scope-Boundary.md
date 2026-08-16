# RC5 Known Limitations and Scope Boundary

## 本轮不构成阻塞的 NOT IN SCOPE

| 项目 | 原因 |
|---|---|
| 真实 PDD 登录/页面/Selector | 需要真实平台证据和受控账号 |
| 真实消息 DOM 与角色识别 | 需在真实店铺验证 |
| 真实商品卡、SKU、订单区域 | 需真实页面结构 |
| 输入框、发送按钮和真实 Receipt | 必须最后分阶段开启 |
| 长时间真实运行 | 需 Pilot 负载与网络环境 |
| 代码签名、企业证书 | 商业发布阶段 |
| Windows Service | 商业发布/运维形态选择 |
| 正式 Release Tag | 当前工作树未提交；以生产树和包 SHA 冻结 |

## 已知限制

- 当前安装实例已与最终候选 ZIP 对齐；真实 PDD 读取和发送仍未验收。
- AI 响应速度取决于本地 Ollama/BGE/向量库；一次完整 UI 验收中 AI 阶段约 37 秒。
- 真实 PDD Adapter 仍需验证平台字段、页面变更、UNKNOWN 处理和失败恢复。
- AUTO_LOW_RISK 框架离线通过，但真实发送 Pilot 初期必须保持 MANUAL_CONFIRM。
- Agent 状态中的 `last_error_code` 是历史最近错误字段；判断当前故障应同时看 runtime status、heartbeat 和后续 `CONNECTION_RECOVERED` 事件。

## 当前没有的离线阻塞

截至本报告，没有遗留的离线 P0/P1 `BLOCKED` 项。
