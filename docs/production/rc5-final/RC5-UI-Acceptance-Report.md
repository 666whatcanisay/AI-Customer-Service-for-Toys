# RC5 Green Assistant UI Acceptance Report

## 结果

绿色客服助手最终界面验收为 **PASS**。

| 验收项 | 结果 |
|---|---|
| 会话列表显示客户、时间、状态 | PASS |
| 客户消息窗口显示 | PASS |
| AI 回复草稿显示 | PASS |
| 风险等级、质量状态、策略显示 | PASS |
| 3 条知识依据显示并可查看 | PASS |
| MANUAL_CONFIRM 人工确认入口 | PASS |
| 人工确认后端生成 ExecutionPreparation | PASS |
| 最终界面显示“执行已准备，尚未真实发送” | PASS |
| 刷新后不恢复成重复确认/重新生成状态 | PASS |
| 将准备状态误写成已发送/Receipt | 已修复并 PASS |
| 真实 PDD 读取与发送 | NOT IN SCOPE；始终关闭 |

## 后端联合证据

- Conversation：`rc5-ui-synthetic-positive-02`
- Decision：`decision-0d90d9e31d84492a95f484b1c43788f7`
- Preparation：`execution-preparation:a0689b273101292cf0ed58a86ef48b7fa24e7cdde5cf67408ff13777258f851e`
- 状态序列：`WAITING_APPROVAL → HUMAN approval → EXECUTION_PREPARED`
- Quality Gate：`PASS`；Risk：`LOW`；Policy：`MANUAL_CONFIRM`
- 真实 execution/receipt/send：全部 `0`

## 当前验收 UI 哈希

| 文件 | SHA256 |
|---|---|
| `ui/index.html` | `1a34f5721b0b8454c6535c1a88a4ce9e06e9006f5ae09b42ad9782e09236c6d2` |
| JavaScript | `2298c0d73d4325f7487e38c8c68f18924eeaa2ef453bba3cacb04ee9a3122835` |
| CSS | `02cab63d59c65e3e780dc1811c9e8bc58d63c0cb5a5a397c04da213f41f7b25b` |

最终候选包引用同一 JS/CSS；其 `index.html` 额外包含打包阶段注入的品牌 favicon，因此外壳 HTML SHA 不同，这是预期包装差异，不是应用代码差异。
