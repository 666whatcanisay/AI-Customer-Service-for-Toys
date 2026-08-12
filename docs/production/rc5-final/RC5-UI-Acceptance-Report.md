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

## 当前候选及安装实例 UI 哈希

| 文件 | SHA256 |
|---|---|
| `ui/index.html` | `e4bf0e3a11ba1dbd3aff3555d8f5da459a0b0822604ae8e6251d91f748bc4efd` |
| JavaScript | `7de0181e8876b2be52ea5c77391ecf0aa634f163d6bbde65bd5febdbdc56a91a` |
| CSS | `fab18c8d7784ba2d79118fe8a98d23634029303cdc08f8d40896f66db213a91c` |

当前安装实例已事务式升级为最终候选包，UI 文件与候选包一致。人工联合验收使用同一绿色助手业务链；升级后又完成 214 项 UI 回归与类型检查。
