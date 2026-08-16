# RC5 Issue Resolution Report

| 编号 | 等级 | 问题 | 根因 | 修复 | 验证 | 状态 |
|---|---|---|---|---|---|---|
| RC5-001 | P0 | ExecutionPrepared 被 UI 写成已发送并生成回执 | preparation/receipt 字段语义混用 | 分离准备与回执展示，准备状态不显示“标记完成” | 前端测试 + 人工 UI + 后端零发送计数 | CLOSED |
| RC5-002 | P1 | 刷新后已准备会话恢复成可重复确认 | 本地 workspace 未接受后端 prepared 状态 | 同步 preparation 后固化 draft；禁用 review/regenerate | 前端测试 + 刷新界面验收 | CLOSED |
| RC5-003 | P1 | 热启动证据嵌套对象无法 JSON 序列化 | 仅处理顶层模型 | 递归处理 model/dict/list/tuple | Engine 单测和全量回归 | CLOSED |
| RC5-004 | P1 | 跨仓合同校验在清空 PYTHONPATH 后导入失败 | 未显式加入 Engine `src` | 解析根目录后注入 sys.path | Gateway 目标测试 + Engine 全量 | CLOSED |
| RC5-005 | P1 | 新候选 ZIP 无法复用部署验收脚本 | 测试脚本硬编码旧 SHA | 增加 `ExpectedArchiveSha256` 参数 | Windows 13/13 | CLOSED |
| RC5-006 | P1 | 手工模拟入口在真实 Agent 模式被拒绝 | 安全设计如此，不是后端缺陷 | 改用正式 Synthetic Provider 注入 | 正向闭环 PASS | CLOSED（按设计） |

本轮没有只记录未修复的离线 P0/P1 问题。

