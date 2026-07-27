# LONG RUN V10 — 夜间冲刺执行结果

执行基线：`origin/develop@32feb6108156f5fb4ec297417537d60452d0743f`。

## 已完成候选

| 线路 | 提交 | PR | 结果 |
| --- | --- | --- | --- |
| Control / Interface Owner | `5dceecf` | [#58](https://github.com/666whatcanisay/AI-Customer-Service-for-Toys/pull/58) | 冻结 `ai-control.v1`；明确 C 必须解包 A 的 `data.modules`。 |
| C Admin | `ec2cc84` + `4a155bf` | [#55](https://github.com/666whatcanisay/AI-Customer-Service-for-Toys/pull/55) | 移除空枚举查询参数，且只接受 A 的真实 success envelope。 |
| B Customer | `8630c4e` | [#57](https://github.com/666whatcanisay/AI-Customer-Service-for-Toys/pull/57) | 锁定 `/feedback → FeedbackGuide` 路由回归，不改变反馈协议。 |
| A AI | `2ac537f` | `ENV_BLOCKED_CREATE_PR` | 限制模型输出长度并兼容 JSON 围栏；现已推送 `codex/rag-night-p1`。 |
| OPS Runtime | `6e4ad61` | [#56](https://github.com/666whatcanisay/AI-Customer-Service-for-Toys/pull/56) | 运行记录加入仓库根、SHA、来源指纹与模式；旧/不匹配记录不再冒充当前版本。 |

## 真实与回归证据

* A 实例 `8000` 的模块接口真实返回五个模块，形状为 `success.data.modules`；此前 C Consumer 错误读取为零模块的根因已修复。
* C 实例 `8011` 对 `review_status=` / `evaluation_status=` 返回 422，证明其对空枚举严格校验；C 候选在客户端省略空值。
* 当前 `5173` 与 `5174` 均 HTTP 200，但运行的是旧 `develop@3b9f3e6`；旧 B 未含 `/feedback`，旧 C 未含新解包逻辑。这是运行版本未更新，不是候选代码失败。
* C：typecheck、Vitest `33 passed`、production build、`git diff --check` 通过。
* B：typecheck、聚焦 Vitest `10 passed`、production build、`git diff --check` 通过。
* A：结构化输出解析 `6 passed`，后端 `77 passed, 3 skipped`；本地 `qwen3.5:9b` 对去标识化合成输入 smoke 通过，未读写 C。
* OPS：新来源记录回归、29 个 PowerShell 语法检查、Admin 生命周期、runtime-fix2 和 target-pilot 回归通过。完整 OPS 套件未通过：既有 `Test-OpsT04Fix1` 在假运行时夹具的重复 health 探针中超出时间盒，不能声称全量通过。

## 严格未完成项

1. A Draft PR 未创建：GitHub GraphQL TLS 握手超时；分支已安全推送，按规则记录为 `ENV_BLOCKED_CREATE_PR`，不阻断代码审查。
2. OPS 仍需定位或隔离 `Test-OpsT04Fix1` 的超时后，才能作为全量运行时回归通过。
3. 候选尚未审查/合并；正式服务不能凭候选分支更新。
4. 因未合并、未确认无人使用系统，未执行正式停止/重启。当前服务保持运行且未受本轮影响。
5. A 的真实 C→A→C 验证仍需要隔离 C 中人工确认、去标识化的 `ANALYZING` 快照；合成 qwen smoke 不替代该 Gate。
6. 内部试运行外部 Gate 仍保留：当前 Private 子网 TCP 5173 防火墙规则和第二台受控客服电脑的 TCP/浏览器验收。

## 下一步（不自动执行）

1. 审查 #55、#57、#58；A PR 网络恢复后创建并审查；#56 在 OPS 全量回归明确后审查。
2. 仅在用户确认没有人在使用页面时，按正式 OPS 安全停止/启动流程把已合并的 `develop` 重启。
3. 重启后核对运行记录 SHA 与 `develop` 一致，再验证 `/feedback`、Admin 模块列表、C 两个筛选页、B→C 反馈以及 C→A→C 人工确认的隔离闭环。

## Gate

`NIGHT_SHIFT_RESULT = CONDITIONAL_PASS / INTEGRATION_BLOCKED`。

原因：P0/P1 候选和范围/定向验证已经交付；但尚未完成代码审查合并、OPS 全量回归、当前版本安全重启及完整真实闭环。因此不能声明 `INTERNAL PILOT READY`。
