# AI-CS Runtime Entry Alignment V1 Task Card

任务：`BUG-RUNTIME-002 / Windows Runtime Entry Alignment V1`

目标：让运营人员使用通用 PowerShell 命令或 `scripts/windows` 中文双击入口时，自动操作当前正式 LOCAL/LAN Runtime，不再因入口模式或配置路径错配而失败。

范围：`scripts/windows/**`、对应 OPS 测试、Bug/状态/交接文档；不包含 A/B/C 业务代码、UI、contracts、数据库结构或数据、Prompt、模型、RAG、R006/R009 逻辑、防火墙配置。

所有者：OPS 实施；Control 管理 Gate；QA 执行隔离脚本回归和正式 stop/start/status 验收。

成功标准：通用 start/status 自动沿用受管 `network_mode`；中文入口能解析正式配置；四服务恢复为同 SHA、clean、standard/LAN、健康；A ready/model configured、活动集合 47 chunks；失败仍安全清理。

风险与缓解：错误模式选择可能制造混合监听 → 只信任同仓库一致的受管记录，混合记录拒绝执行；配置回退可能误用其他目录 → 仅允许当前仓库内固定 `.runtime` 路径；真实验收涉及短暂停服 → 先完成隔离测试，再用官方受管 stop/start，禁止按端口强杀。

验收：PowerShell 单元/静态回归、无写入已运行态 start/status、正式受控 stop→通用 start→status、四服务 HTTP/API Smoke、Git diff/clean/同 SHA。Gate 为 `RUNTIME_ENTRY_ALIGNMENT_COMPLETE`；任一身份或健康检查失败则 `BLOCKED` 并回滚现有 Runtime。
