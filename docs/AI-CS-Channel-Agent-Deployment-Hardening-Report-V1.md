# AI-CS Channel Agent Deployment Hardening Report V1

## 技术结论

`AI-CS-Agent 1.0.0-rc.2` 已完成 Windows 部署加固。启动、运行与状态命令现在统一遵守 0–5 退出码；配置错误、Gateway 不可达、认证失败、Runtime 异常与浏览器环境错误不再被折叠或误报为成功。Windows 专项测试 **22 passed**，全仓回归 **412 passed**；最终 ZIP 的 1,046 个清单文件哈希全部匹配。

## 1. 问题原因

发现并修复了五个相互叠加的问题：

1. 构建脚本使用 `zipapp -m ai_cs_agent.cli:main`。生成的 ZIP 根入口只调用 `main()`，没有 `raise SystemExit(main())`，导致 Python 函数虽然返回非零值，Windows 进程仍以 0 退出。这是部署验证问题的直接根因。
2. `AgentRuntime.run()` 将所有启动失败统一返回 2，无法区分配置、认证、Runtime 与 Browser 错误。
3. `status` 只在 `AgentStatus=FAILED` 时返回非零；`DEGRADED + GATEWAY_UNAVAILABLE` 会错误返回 0。
4. `configure` 与启动超时使用了和新规范冲突的旧返回码。
5. Windows 上状态查询与状态文件原子替换可能短暂竞争，触发 `PermissionError`，使正常启动被误判为 Runtime 错误。

## 2. 修复内容

- 新增统一 `ExitCode` 模型，并把 `exit_code`、Agent 版本、配置状态持久化到 Runtime State。
- 配置、Gateway、认证、Runtime 和 Browser 异常由同一个分类器处理；心跳退化状态也保留对应非零码。
- Gateway Health 的 HTTP 401/403 与冻结 Error Envelope 中的认证错误映射为认证失败，不修改 Gateway Contract V1。
- `start` 在创建子进程前清除陈旧 FAILED 状态，启动失败时输出中文原因并传播子进程退出码。
- `status` 展示版本、配置、Agent、Gateway、Gateway 版本、Browser、Session、Kill Switch 与中文错误，并在 FAILED/DEGRADED 时返回对应非零码。
- `stop` 正常关闭返回 0；安全超时返回 4。Kill Switch 默认开启并继续阻断 Execution。
- ZIP 根入口显式执行 `raise SystemExit(main())`；BAT 使用 UTF-8 BOM + CRLF，确保 `cmd.exe` 正确解析中文。
- Runtime State Store 增加同进程互斥和最多 5 次、总等待不超过 200ms 的 Windows 文件占用重试；超过上限仍 fail-closed 为 4。

## 3. 退出码规范

| 退出码 | 含义 | 典型触发 |
|---:|---|---|
| 0 | 正常 | 启动成功、状态正常、正常停止、Kill Switch 命令成功 |
| 1 | 配置错误 | 配置缺失、格式错误、安全策略不合规 |
| 2 | Gateway 不可达 | 网络失败、连接超时、Gateway 报告不健康 |
| 3 | 认证失败 | Windows Credential 引用不可用、签名被拒绝、401/403 |
| 4 | Runtime 异常 | 未预期异常、契约响应错误、启动/停止安全超时 |
| 5 | 浏览器环境错误 | Chrome 不可用、独立 Profile 初始化失败 |

## 4. Windows 用户体验

首次运行路径保持为：环境检查 → 配置检查 → Gateway 检查 → Browser 检查 → Ready。错误不再输出技术堆栈，而是给出中文操作提示，例如：

```text
AI-CS Agent 启动失败（退出码 3）：AI-CS 凭据引用不可用，请检查 Windows 凭据管理器。
```

`status` 示例字段：

```text
版本: 1.0.0-rc.2
配置状态: VALID
Agent 状态: FAILED
Gateway 状态: AUTHENTICATION_FAILED
Gateway 版本: UNKNOWN
Browser 状态: UNKNOWN
Session 状态: UNKNOWN
Kill Switch: ENABLED
错误: AI-CS 凭据引用不可用，请检查 Windows 凭据管理器。
```

## 5. 测试结果

| 范围 | 结果 |
|---|---:|
| Windows Agent 专项 | 22 passed |
| 全仓回归 | 412 passed，1 warning |
| 退出码 0–5 | 6/6 符合 |
| ZIP 清单哈希 | 1,046/1,046 匹配 |
| ZIP 缺失/额外文件 | 0/0 |
| BAT 编码与换行 | UTF-8 BOM + CRLF，PASS |
| ZIP 入口退出码传播 | PASS |

包级黑盒验证：缺配置的 `run/status` 返回 1；缺凭据的 `run/start/status` 返回 3；未运行时 `stop` 返回 0；`kill-switch enable` 返回 0。Gateway 不可达返回 2、Runtime 异常返回 4、Browser 环境错误返回 5 均由专项测试验证。

全仓唯一 warning 来自 Starlette/FastAPI TestClient 的第三方弃用提示，不影响本次退出码或打包结论。

## 6. 发布影响

- 新制品：`AI-CS-Agent-1.0.0-rc.2-windows-x64.zip`
- SHA-256：`f2f75409d149a2f7dea7b883c5feb7ac5a3928e9ad47cef202c5539aa3abba01`
- ZIP 大小：17,146,357 bytes
- 包内文件：1,047；其中 1,046 个由 release manifest 逐文件校验，另 1 个为 manifest 本身。
- `dist/windows-rc` 中旧 rc.1 构建产物已被 rc.2 替换；源码、测试、历史文档和保护锚点未删除。
- Runtime State 对旧状态文件向后兼容：缺失 `exit_code` 时由状态和错误信息推断。
- 未修改 Gateway Contract V1、AI-CS Server、PDD 组件或执行审批链。

## 7. 限制与风险

- 本任务没有使用真实 AI-CS 凭据，因此“可达且认证成功”的非生产 Gateway 需要在后续授权环境验证。
- ZIP 尚未进行企业 Authenticode 签名，也不是 MSI 或 Windows Service。
- 跨进程状态文件占用采用有界重试；持续超过 200ms 时会安全失败并返回 4。
- 未连接真实 PDD、未登录真实账号、未发送客户消息。

## 8. 下一步建议

1. 在干净 Windows VM 上运行 rc.2 的安装、重启、断网和恢复矩阵。
2. 使用专用非生产凭据验证 Gateway 退出码 0、2、3 的端到端行为。
3. 增加 Authenticode、MSI/Windows Service 与日志轮转策略。
4. 冻结 rc.2 发布清单并建立回滚到上一个已签名制品的 Runbook。

## 9. 待冻结问题

- 正式宿主采用 Windows Service、计划任务还是托盘应用？
- 企业代码签名证书、发布渠道和吊销机制由谁负责？
- 状态存储何时从单文件升级为 Windows Service 级持久化？

Final Status: `CHANNEL_AGENT_DEPLOYMENT_HARDENED`
