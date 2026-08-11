# AI-CS Channel Agent Store Platform Binding Checkpoint

日期：2026-08-11

状态：`SOURCE_CHECKPOINT_READY / RUNTIME_NOT_MIGRATED`

## 结果

C 平台后端和 B 客服工作区已经完成 Channel Agent 所需的“AI-CS 内部 Store 与平台店铺 ID 分离”源码收口：

- `store_code` 继续作为 AI-CS 内部业务标识。
- `platform_store_id` 是 PDD 页面观察得到的平台身份，不能与 `store_code` 直接比较。
- `store_platform_bindings` 保存经人工确认、可审计、可撤销的精确映射。
- 同一个有效 `platform + platform_store_id` 不能同时绑定到两个内部 Store。
- Device Setup 与桌面布局只接受 ACTIVE 精确绑定，不按店铺名称猜测。
- 选择当前店铺仍需人工确认；映射成功不授权消息发送。
- 0018 只回填已有可靠 `platform_store_id` 元数据；冲突会中止迁移并要求人工处理。

## 交付边界

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| C schema/model/service/API | 完成 | 严格输入、RBAC/Store scope、审计与撤销语义 |
| 0017 pairing rotation audit | 完成（源码） | 不保存配对明文 |
| 0018 Store platform binding | 完成（源码） | 可升级/降级/再升级测试 |
| Desktop Agent projection | 完成 | 返回内部 Store 和 ACTIVE 平台绑定 |
| B Device Setup 精确匹配 | 完成 | 未绑定、错配、多匹配均失败关闭 |
| B Channel Agent assistant event 刷新 | 完成 | SSE 触发即时刷新，轮询保留为降级路径 |
| 正式 Runtime 数据库迁移 | 未执行 | 必须单独备份、停写、迁移、回滚演练 |
| 真实 PDD 联通 | 未执行 | 本 checkpoint 不连接真实 PDD |
| 自动/受控发送 | 未启用 | 继续要求人工审核；发送属于独立 Gate |

本 checkpoint 不修改正式数据库、不切换运行服务、不写入真实平台身份，也不把测试夹具或页面内存会话描述为真实客户数据。

## 验证记录

- Platform Backend 全量：`173 passed`。
- Store platform binding / desktop workflow 定向：`27 passed`。
- Customer Frontend：typecheck PASS；`44 files / 205 tests passed`。
- Customer Frontend production build：PASS。
- Customer Frontend channel-agent build：PASS。
- 仅存在 Vite 大 chunk 提示和既有 Python 依赖弃用提示，无测试或构建失败。
