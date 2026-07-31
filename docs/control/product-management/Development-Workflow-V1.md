# AI-CS Development Workflow V1

```text
提出需求
  ↓
Requirement Registry 登记、去重与边界确认
  ↓
Runtime Gate：目录 / branch / SHA / clean / DB / contracts
  ↓
创建单一任务分支和 Task Card
  ↓
先记录 Bug 或冻结 Interface，再实施
  ↓
单元/集成/浏览器测试
  ↓
隔离数据验收；正式写入须单独授权和备份
  ↓
Task Gate 复核、Release Notes、machine-context
  ↓
选择性提交、推送、受控发布
```

## 强制规则

1. 一个任务卡对应一个主要目标，不把 R006、R009、RAG 发布或 Runtime 切换混在同一提交。
2. 禁止 `git add .`；按 A/B/C/OPS/Control 所有权选择性提交。
3. 数据库、向量、日志、依赖、构建产物、真实 Excel 和截图不进入 Git。
4. 浏览器写入测试默认使用隔离 Runtime；正式端口只做只读检查，除非任务明确授权。
5. 自动测试通过不能替代真实 Runtime 身份和浏览器业务 Gate。
6. 未关闭 P0/P1 时只能给出条件通过或阻塞状态。
