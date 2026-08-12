# RC5 Issue Resolution Addendum（多轮最终验收）

| 编号 | 等级 | 问题 | 处理 | 验证 | 状态 |
|---|---|---|---|---|---|
| RC5-007 | P1 | Runtime 重启后旧绿色窗口本地认证失效 | 增加一次性 Bootstrap handoff，不保存 Cookie/CSRF | Desktop/Windows 针对测试与现场恢复通过 | CLOSED |
| RC5-008 | P1 | 固定多轮验收会话未包含在最终定向清理范围 | 清理选择器同时校验固定 conversation_id、provider_id、provider_kind | 9 项历史/清理测试；现场清理 PASS | CLOSED |
| RC5-UI-001 | P2 | Agent 重启后可能额外打开蓝色登录窗口 | 已增加恢复标记与 15 秒兜底，但当前 Edge 现场仍可出现额外窗口；采用人工关闭 | 后端、原绿色窗口和保护状态不丢失 | ACCEPTED LIMITATION |
| RC5-UI-002 | P2 | 切回人工后顶部策略下拉显示可能滞后 | 不再重启现有实例；当前 Turn 与后端 Policy 为权威状态 | 后端 Revision=3、Turn=MANUAL_CONFIRM、HUMAN Preparation READY | ACCEPTED LIMITATION |
| RC5-STAB-012 | P0 | 覆盖升级在旧进程文件锁下可能形成混合安装目录 | 新包先验签暂存；等待安装目录进程退出；目录级切换；失败回滚 | 安装器 17 PASS、隔离部署 13/13、当前实例候选一致 | CLOSED |
| RC5-STAB-013 | P1 | 嵌入式 Python bytecode 缓存膨胀并触发 Windows 长路径失败 | 运行自检后定向移除 `__pycache__`/`.pyc` | 包内缓存 0、1161 文件、独立运行和隔离部署 PASS | CLOSED |

`RC5-UI-001/002` 不阻塞真实 PDD 只读 Pilot，但在允许任何真实自动发送前应重新验收。
