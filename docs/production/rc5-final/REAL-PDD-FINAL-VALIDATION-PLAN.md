# REAL_PDD_FINAL_VALIDATION_PLAN

## 总原则

真实 PDD 只替换 Provider/Send Adapter，不修改已冻结的 AI 客服核心。严格逐 Gate 放行，任何阶段失败立即关闭真实能力并保留证据。

## Gate 1：REAL_PDD_READ_READY

保持 `real_send=false`，只验证：登录状态识别、店铺识别、会话/消息读取、买家/客服角色、商品卡、SKU、订单/物流区域、Cursor/去重和断线恢复。

通过标准：连续受控样本不漏、不重、不串店；字段证据可追溯；不产生任何写操作或发送 Receipt。

## Gate 2：REAL_PDD_AI_READY

真实消息进入已冻结核心：Provider → Agent → Host → Context → AI-CS → Quality Gate → 客服助手。

通过标准：客户、店铺、商品、SKU、订单上下文正确；AI 答案和引用正确；低质量/缺知识/高风险安全拦截；无真实发送。

## Gate 3：REAL_PDD_CONFIRM_READY

模式固定 `MANUAL_CONFIRM`。客服在助手中确认，系统生成 ExecutionPreparation，但 Send Adapter 仍 dry-run/disabled。

通过标准：Decision → HUMAN approval → EXECUTION_PREPARED 唯一且幂等；权限、店铺、会话、过期和 Kill Switch 全部有效；准备状态不写真实 Receipt。

## Gate 4：REAL_PDD_SEND_READY

只选白名单店铺、白名单客服、白名单低风险测试会话，人工逐条授权开启真实发送。AUTO_LOW_RISK 仍关闭。

验证：输入框/发送按钮 Selector、发送前二次校验、真实 Receipt、失败/UNKNOWN、重复防护、重启恢复和长时间运行。

通过标准：已授权消息准确发送一次；真实回执可核对；失败不误报成功；至少完成约定长稳窗口且无漏发、重发、串店或绕过安全门。

## 完成后的交付结论

只有四个 Gate 全部 PASS，并完成长稳、回滚和安全复核后，才可把状态改为 `AI_CS_PRODUCTION_READY`。若没有新增 P0/P1 问题，完成这些真实 PDD 验证后可以正式交付。

