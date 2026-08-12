# RC5 Change Impact Report

## 本次最小修改

| 变更 | 原因 | 影响范围 | 回归 |
|---|---|---|---|
| UI 将 preparation 与 receipt 分离 | 界面曾把“执行准备”误写成“已发送并生成回执” | `DecisionCenter.vue` 及测试 | Frontend 213 PASS；人工界面验收 PASS |
| 刷新后恢复 EXECUTION_PREPARED | 刷新后草稿曾回到可重复确认状态 | `ReplyAssistantPanel.vue`、`HumanInLoopWorkspace.vue` 及测试 | Frontend 213 PASS；刷新后无重复确认按钮 |
| 热启动证据递归 JSON 化 | Pydantic/嵌套对象无法稳定写入证据 | `run_rc5_hotstart_validation.py` 及单测 | Engine 734 PASS |
| 跨仓校验注入 Engine `src` | 清空 PYTHONPATH 时脚本无法导入 Engine | `validate_ai_cs_channel_engine_integration_v1.py` | Gateway 目标测试及 Engine 全量 PASS |
| Windows 部署测试支持候选包 SHA 参数 | 旧硬编码 SHA 无法验证新候选包 | `test_rc5_windows_deployment.ps1` | 隔离部署 13/13 PASS |

## 未修改的核心

Provider 合同、ACK/Cursor、Agent Identity、Device Binding、Gateway wire protocol、Host 状态机和 Execution 安全门未重构。

## 运行实例影响

- 当前 Agent 进程未因最终 UI 验收被关闭或替换。
- Identity、Binding revision、Profile identity hash 和 PDD Session 文件数量保持不变。
- 只把最终前端构建产物热刷新到受保护验收实例；真实 PDD 浏览器和发送能力始终关闭。
- Pilot 不复用当前安装目录，必须使用 BOM 指定候选 ZIP。

