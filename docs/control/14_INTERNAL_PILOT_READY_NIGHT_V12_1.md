# INTERNAL PILOT READY Night V12.1 候选报告

日期：2026-07-27
控制基线：`origin/develop@f5fccfd9685440f0e43ee5be35207ab4372f6a2d`

## 结论

当前结论为 **`PILOT_CANDIDATE_READY`，尚不是 `INTERNAL_PILOT_READY`**。

本轮已完成 A、B、C/Data Steward、OPS 与集成 QA 的真实核验和三个独立修复候选。候选尚未合入 `develop`，因此不能把候选修复的效果写成正式运行结果。当前正式隔离实例为 `f5fccfd`，四项服务均健康，但其状态脚本仍会把历史 `47/47` 同步记录误当成当前 A 向量统计；实时旧端点实际显示 0 条。这正是 A/OPS 候选要消除的误报。

## 本轮交付候选

| 线路 | 提交 | Draft PR | 内容 | 已验证 |
| --- | --- | --- | --- | --- |
| A | `0ea749c` | #61 | 合并主集合与冻结测试集合的可查询知识计数；初始化异常只暴露稳定错误码 | 专项 27 passed；后端 79 passed、3 个 opt-in E2E skipped；真实 qwen smoke |
| C / Data Steward | `99d77bc` | #59 | Admin 中文业务标签、真实空/错误状态、资料预检清单 | Admin typecheck；Vitest 34 passed；build；C 专项 pytest 22 passed（1 条既有弃用警告） |
| OPS | `af9d09a` | #60 | 将历史同步记录与实时 A 知识统计分开显示，并显式报告 `MISMATCH`/`UNAVAILABLE` | PowerShell 全量语法；OPS 回归；本地/LAN 状态只读验证 |
| B | 无代码变更 | — | 复核真实客服流程、同源代理、错误恢复与人工边界 | typecheck；Vitest 100 passed；build |

上述提交均未修改 `contracts/**`、数据库迁移、ERP、退款、自动发送、自动订单修改、自动 Prompt 修改或自动知识发布；未包含运行记录、日志、向量库、测试包、构建产物或敏感数据。

## 真实验证证据

### 服务与版本

当前隔离运行实例的运行记录均验证为 `f5fccfd`、源码 `CLEAN`：

- C：`127.0.0.1:8011`，`RUNNING + LISTENING`，health 200；测试目录为 1 店铺、5 商品、18 SKU；冻结 RAG export 为 47 项。
- A：`127.0.0.1:8000`，`RUNNING + LISTENING`，health 200，`ready=true`，`model_configured=true`，模型为 `qwen3.5:9b`。
- B：`127.0.0.1:5173`，`RUNNING + LISTENING`，页面、`/rag-api/api/health` 和 `/platform-api/health` 均为 200。
- Admin：`127.0.0.1:5174`，`RUNNING + LISTENING`，运营概览显示 1 店铺、5 商品、18 SKU、16 FAQ、8 安全规则和 1 个导入批次。

### 客服真实页面

使用 B 的真实浏览器页面完成：选择测试店铺和商品 → 输入年龄/安全问题 → 获取真实 qwen 回复 → 记录“直接采用” → 复制回复。回复包含“6～12岁”、小颗粒和成人陪同限制；显示 6 条来源、`CONTROLLED_ANSWER`、`SUGGESTION_ONLY` 和 `AUTO_SEND_DISABLED`。页面要求人工核对和复制，未触发客户发送、退款或订单修改。

对 B 实际代理路径 `POST /rag-api/api/chat` 使用 UTF-8 请求体重放四次（无 SKU 三次、带 SKU 一次）也均返回 `CONTROLLED_ANSWER`、`HIGH`、空 `required_fields` 和 6 条相关来源。此前的转人工结果来自 PowerShell 的中文请求编码差异，已撤销为模型质量故障证据。

### C / A 闭环

既有隔离验证已使用去标识化测试数据完成：案例 `NEW → REVIEWING → APPROVED → EVALUATED`，反馈 `NEW → ANALYZING → ANALYZED`，并有真实 qwen 的 `evaluation_run_id` / `analysis_run_id`、模型版本、Prompt 版本与证据版本。Admin 可查看对应案例和 AI 问题；本轮未新造客户数据。

## 必须处理的 Gate

1. **候选合并与正式重启。** PR #59、#60、#61 仍为 Draft，未获授权合入。合并后必须用正式 OPS 脚本在干净、可信记录的实例上重新启动并确认 A 的实时知识计数为 47，而不是引用历史同步 JSON。
2. **受控网络防火墙。** 当前未配置唯一允许的 `AI Customer Service LAN 5173 (Private)` 当前子网规则；当前会话没有管理员权限，未绕过 UAC 或修改防火墙。不得开放 8000、8011、5174，也不得关闭防火墙。
3. **第二台受控客服电脑。** 在规则正确后执行 `Test-NetConnection <服务器IPv4> -Port 5173` 并访问 `http://<服务器IPv4>:5173/`，完成一次人工问答/复制/案例或反馈验收。若公司网段不可路由，记录 `NETWORK_SEGMENTED`，不把它误判为代码失败。

## 后续建议顺序

1. 审查并合并 #61、#59、#60（A/C/OPS 均与 `f5fccfd` 对齐，彼此不触及相同文件）。
2. 使用正式脚本执行一次可信的停止 → 启动 → 状态检查；保留 Ollama，不处理未知进程。
3. 验证 C/A/B/Admin 与两条同源代理，确认 A 实时统计、B 人工边界和 Admin 中文运营页。
4. 在管理员授权下仅配置 Private/当前子网 TCP 5173，再完成第二台电脑人工验收。

在以上四步完成前，项目不应声明为 `INTERNAL_PILOT_READY`。
