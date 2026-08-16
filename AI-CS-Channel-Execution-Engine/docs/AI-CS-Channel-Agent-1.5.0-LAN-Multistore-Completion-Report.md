# AI-CS ChannelAgent 1.5.0 局域网与多店铺完成报告

## 完成状态

`CHANNEL_AGENT_1_5_0_LAN_MULTISTORE_READY`

## 客户端定位

ChannelAgent.exe 已从设备连接器收敛为客服电脑客户端，负责托盘驻留、首次连接、设备身份、独立浏览器、当前店铺、桌面助手与本地临时状态。AI、RAG、知识、业务数据和审计仍由 AI-CS 服务端负责。

## 首次连接

首次安装不会写入占位生产配置。流程为：

`发现主机 → 展示主机身份/地址/证书指纹 → 输入一次性连接码 → 人工确认 → 写入 Windows Credential Manager 引用 → 注册设备`

连接码 5 分钟失效、最多 5 次尝试且单次使用。客户端配置只保存凭证引用和 CA，不保存设备密钥明文。

## 状态模型

- `INSTALLED`
- `CONNECTED`
- `BOUND`
- `STORE_SELECTED`
- `PDD_READY`
- `ASSISTANT_READY`
- `DEGRADED`

托盘、状态命令与桌面助手使用同一派生状态。

## 多店铺

- `authorized_store_ids`：管理员授权给用户/设备的店铺集合。
- `active_store_id`：客服本次工作的唯一店铺。
- 多店授权后必须由客服显式选择，不自动挑选第一家。
- 页面观察店铺必须与活动店铺完全一致。
- 存在待审核、RUNNING 或 UNKNOWN 工作流时禁止切店。
- 心跳上报授权集合和唯一活动店铺，服务端拒绝越权或状态漂移。

## 局域网部署

主机脚本一次启动 AI-CS 客服服务、Channel Engine V2 控制端和 UDP 发现服务。控制端使用 TLS；Windows 防火墙仅放行 Private 网络与 LocalSubnet。客户端必须核对主机并人工输入连接码，禁止发现后自动绑定。

## 数据最小化

客户端长期保存：Agent 状态、店铺状态、游标、凭证引用和必要恢复信息。完整聊天、订单和商品业务数据以服务端为唯一数据源；本地助手 feed/缓冲为短期缓存，默认 30 分钟过期并在安全停止时清理。Receipt、审计和恢复 checkpoint 不被清理。

## 验收结果

- 设备签名、重放攻击、连接码、证书确认、多店铺与本地保留策略：23 项定向测试通过。
- 桌面 UI 类型检查、布局测试与生产构建通过。
- Synthetic PDD 全链路通过，耗时 6.184 秒，Receipt 为 SUCCESS。
- 全量 Python 回归：623 项通过、1 项显式 Edge 人工烟测跳过、0 失败。
- Contract + Security 专项：140 项通过。
- Windows 1.5.0 ZIP 构建成功；空白目录完成安装、版本、首次启动状态及卸载验证。
- 发布包 SHA256：`36d2fc877f2f6dc484fee833f126d3c14b0b08d78ca748a300eaa82f32500f86`。
- Gateway Contract V1 canonical SHA256 保持 `e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5`。
- 真实 PDD 未连接、未登录、未读取、未发送。

## 已知限制

首次真实 PDD 扫码、店铺身份匹配和真实消息观察必须等客服在场后人工验收。当前发布包不包含真实 PDD 读写实现，真实发送默认关闭。
