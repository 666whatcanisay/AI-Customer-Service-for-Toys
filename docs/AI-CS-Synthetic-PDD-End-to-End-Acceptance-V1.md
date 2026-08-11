# AI-CS Synthetic PDD 全链路验收 V1

## 结论

ChannelAgent 1.5.0 已完成以下本地仿真闭环：

`模拟买家发送消息 → ChannelAgent 捕获 → Synthetic PDD Adapter → CustomerContext → AI-CS Gateway → AI Reply Package → 桌面助手 → 仿真确认发送 → 不可变 Receipt`

验收状态：`SYNTHETIC_PDD_E2E_READY`。

本次未连接真实 PDD、未读取真实客户数据、未发送真实消息。

## 仿真上下文契约

契约版本：`synthetic-pdd-contract.v1`。

仿真页面提供与真实适配器相同形状的必要上下文：

- 店铺：平台、店铺 ID、店铺名称、客服身份。
- 商品：商品 ID、商品名称、类目、适用年龄。
- SKU：SKU ID、名称、颜色、包装、适用年龄。
- 订单：订单 ID、订单状态、物流状态、售后状态；不含地址和支付数据。
- 会话：会话 ID、脱敏客户标识、双向消息、时间和顺序号。

适配器统一转换为现有 `CustomerContext`；未来切换渠道时只替换 Adapter，不改 AI、审批、执行和 Receipt 链路。

## 安全边界

- `manual_approval_required=true`
- `auto_reply_enabled=false`
- `real_send_enabled=false`
- `real_platform_connected=false`
- `customer_message_sent=false`

仿真自动确认只允许在 `SIMULATOR` 模式、`SIM-*` 店铺与会话命名空间内运行。任何条件不满足即拒绝执行；UNKNOWN 禁止自动重试。

## ChannelAgent 1.5.0 验收运行

证据目录：`.runtime/synthetic-pdd-e2e/acceptance-agent-1.5.0`

- 输入：`这款香槟玫瑰积木适合8岁的孩子玩吗？需要家长陪同吗？`
- 商品：`【仿真商品】香槟玫瑰积木花束礼盒`
- SKU：`SIM-SKU-AGE8-CHAMPAGNE / 香槟玫瑰花束礼盒`
- AI 结论：适用年龄 8 岁及以上，并提示小颗粒与家长指导风险。
- Receipt：`SUCCESS`
- 端到端延迟：`6.184s`，低于 `20s` 验收门槛。

完整证据包括报告、事件、发送前后助手 feed 及 Receipt，均保存在上述运行目录。
