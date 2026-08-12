# RC5 管理员手册

## 每日检查

- AI-CS、Platform、Host 健康端点正常。
- Agent Identity 为 ACTIVE，Device Binding revision 正确。
- 当前店铺与客服授权匹配。
- Policy 默认 MANUAL_CONFIRM，real_send=false。
- 日志中无持续 AI、Gateway、ACK 或数据库错误。

## 策略管理

- `MANUAL_CONFIRM`：所有建议必须人工确认，只准备执行。
- `AUTO_LOW_RISK`：仅 Quality Gate PASS、低风险、知识充分且所有安全门通过时允许进入自动策略；真实发送仍受独立总开关控制。
- 高风险、UNKNOWN、缺上下文和 Kill Switch 状态必须转人工。

## 知识与店铺

- 发布知识前核对 store_id、product_id、SKU 和有效期。
- 不得把测试店铺知识发布到真实店铺。
- 修改店铺绑定、权限、Gateway 合同或 Migration 必须触发相应冻结模块复验。

## 发布管理

Pilot 只使用 Release BOM 中的 ZIP SHA；升级前后保存版本矩阵、数据库状态和身份/Profile 保护快照。

