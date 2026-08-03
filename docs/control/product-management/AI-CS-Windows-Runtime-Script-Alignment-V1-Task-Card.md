# AI-CS Windows Runtime Script Alignment V1 Task Card

## 目标

让迁移后的`AI-CS`成为Windows运维唯一真实执行源，同时让旧项目目录中的现有快捷方式继续可用，但只作为明确、可审计的兼容跳转入口。

## 范围与Owner

- OPS：`scripts/windows/**`启动、停止、状态、LAN、诊断、后台和防火墙入口。
- Control：旧脚本审计、迁移边界、兼容策略、报告和machine-context。
- QA：语法、路径、配置、兼容跳转、正式启停和四服务身份验收。

允许修改：正式项目与旧项目的`scripts/windows/**`，以及正式项目运维/控制文档。

禁止修改：A/B/C业务代码、contracts、数据库、R006、R009、Prompt、RAG和Runtime业务数据。

## 成功标准

1. 旧目录全部`.ps1`与`.bat`有用途、调用关系、路径依赖和风险清单。
2. 旧运维入口不再启动旧代码，只调用`AI-CS\scripts\windows`对应入口，并明确提示项目已迁移。
3. 新项目五个标准入口只接受`AI-CS` RepositoryRoot，自动解析`green-standard.local.ps1`，不引用旧目录。
4. 启动前可核对Git SHA、配置、Python、Node和pnpm；失败信息可见且不遗留部分服务。
5. 中文BAT使用统一代码页、`ExecutionPolicy Bypass`、保留窗口和退出码。
6. 新目录启动、旧目录兼容启动、停止、状态和LAN模式均通过；四服务最终由`AI-CS`同一SHA运行。

## 风险与停止条件

- 旧仓库存在用户未提交修改：仅选择性修改/提交`scripts/windows/**`，不切换或清理用户工作区。
- 正式Runtime存在已验证服务：在实现和隔离测试通过前不停止；最终只由正式脚本安全停止已验证PID。
- 若数据库revision、RAG collection/chunks或服务身份变化异常，立即停止并按原`a98b448`运行锚点恢复。
- 不按端口结束未知进程，不修改防火墙规则，不删除旧脚本。

## Gate

- 起始Gate：`WINDOWS_RUNTIME_SCRIPT_ALIGNMENT_READY`
- 目标Gate：`WINDOWS_RUNTIME_SCRIPT_ALIGNED_V1`
- 正式基线：`release/product-reliability-hardening-v1@a98b448aa4ab`
- 实现分支：`codex/windows-runtime-script-alignment-v1`
