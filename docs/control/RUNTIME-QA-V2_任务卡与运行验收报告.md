# RUNTIME-QA-V2 任务卡与运行验收报告

日期：2026-07-27
任务：为 AI-CS 建立可核验的实际运行身份与 Runtime Gate。
范围：`scripts/**`、`frontend/**`、`admin_web/**`、`docs/**`；未修改 A/C 后端业务逻辑、共享契约、数据库迁移或依赖锁文件。

## 运行身份约定

浏览器和 Gate 都从同一事实源读取身份：

- B（5173）与 C Admin（5174）由 Vite 插件在 `GET /__runtime-identity.json` 提供产品名、`package.json` 版本、当前工作目录的 Git 短 SHA、源码状态、运行模式和 API 模式。响应带 `Cache-Control: no-store`，因此不会将旧身份缓存为新版本。
- 页面侧栏显示同一组字段，字段缺失时显示“不可用”，不会以默认值冒充实际版本。
- A 不在本轮允许修改范围内、也没有浏览器入口。Gate 用受管进程记录的工作目录 Git 身份，加上 `GET /api/health` 与 `/openapi.json` 的产品名/版本作为 A 入口身份；运行模式明确标记为 `API_ENTRY`。
- `DIRECT`、`SAME_ORIGIN_PROXY`、`HYBRID` 只由实际 API base URL 推导；LAN 模式必须是 `SAME_ORIGIN_PROXY`。

## Runtime Gate

入口：`scripts/windows/Invoke-RuntimeGate.ps1`。

```powershell
# 启动前：允许端口尚未启动，但拒绝未知/混合的受管运行记录
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/Invoke-RuntimeGate.ps1 -Action Preflight

# 运行验收：监听 PID、受管记录、工作目录、Git、浏览器入口、版本身份和 A 健康检查
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/Invoke-RuntimeGate.ps1 -Action Verify -ExpectedGitShortSha <期望短SHA>

# LAN 启动入口会自动传入 -LanMode；不要用本地配置误判 LAN 受管记录
```

Gate 输出可加 `-Json` 供 CI 或人工归档。`-ExpectedGitShortSha` 是可选的版本门槛：运行目录 SHA、页面身份 SHA 或 A 入口 SHA 不一致即失败。普通和 LAN 启动脚本均在启动前调用 `Preflight`。

## 十阶段验收

| 阶段 | 结果 | 事实证据 |
|---|---|---|
| Phase 1/10 扫描 | PASS | 初始 `5173` PID 33884、`5174` PID 33144、A `8000` PID 32632 都来自原工作区，工作目录 SHA 为 `3b9f3e63700b`、状态 `DIRTY`；这与本任务基线 `32feb6108156` 不同。旧 B/C 没有 JSON 身份端点，Gate 不能把它们当作新版。 |
| Phase 2/10 身份显示 | PASS | B 侧栏显示“木木小树 AI 客服工作台 / 1.0.0 / 32feb6108156 / LOCAL / DIRECT”；C 侧栏显示“AI 客服平台运营管理中心 / 0.1.0 / 32feb6108156 / LOCAL / SAME_ORIGIN_PROXY”；A 由 API 身份显示“独立 RAG AI 客服原型 / 1.0.0 / API_ENTRY / DIRECT”。 |
| Phase 3/10 Gate 设计 | PASS | Gate 覆盖启动前受管 PID 检查、浏览器入口 `#app` 检查、无缓存身份 JSON 检查、`package.json` 版本对照、Git 对照及 A health/OpenAPI 对照。 |
| Phase 4/10 实现 | PASS | 新增共享 Vite 身份插件与 Gate；普通/LAN 启动路径注入真实代理目标和运行模式；页面只增加状态显示，不改变业务流程。 |
| Phase 5/10 生命周期 | PASS | 隔离实例 B `15173`、C Admin `15174`、A `18000`、C Platform `18011` 启动；Gate Verify 全部 PASS；B 刷新后身份仍为 `32feb6108156`；隔离 C Platform 已按受管记录停止、恢复并重新核验。原 `5173/5174/8000` 未停止或改写。 |
| Phase 6/10 真实浏览器 | PASS | B 的 `/`、`/ai-chat`、`/suggestions`、`/suggestions/mine`、`/experience-cases`、`/feedback` 全部挂载且各有唯一运行身份；C 的 15 个一级运营路由全部挂载且各有唯一运行身份。 |
| Phase 7/10 异常 | PASS | 旧运行被 `ExpectedGitShortSha=32feb6108156` 拒绝（实际 `3b9f3e63700b`）；将 C Admin 指向未监听的 `15999` 时 Gate 报告 `port is not listening` 和身份端点不可达；停止隔离 C Platform 后，B `/ai-chat` 呈现“数据服务不可用 / 暂时无法完成新的 AI 咨询”，不伪造可用数据。 |
| Phase 8/10 优化 | PASS | 身份端点以 `no-store` 防旧缓存；LAN Gate 使用已解析的 LAN 配置；代理目标改为运行时端口，隔离端口也可真实验收。 |
| Phase 9/10 回归 | PASS | B `vue-tsc --noEmit`、Vitest 24 文件/99 测试、Vite build 通过；C `vue-tsc --noEmit`、Vitest 13 文件/29 测试、Vite build 通过；22 个 Windows 脚本 PowerShell 语法解析通过；`git diff --check` 通过。既有 Vite CJS 和大 chunk 警告未改变。 |
| Phase 10/10 交付 | PASS | 已仅暂存本任务文件、提交并推送 `codex/runtime-qa-v2`，已创建 Draft PR [#53](https://github.com/666whatcanisay/AI-Customer-Service-for-Toys/pull/53)。 |

## 隔离验证快照

最终 Gate Verify（隔离实例）全部通过：

| 线路 | 服务/端口 | 监听 PID | 工作目录 SHA | 页面或 API 版本 |
|---|---:|---:|---|---|
| B | customer-web / 15173 | 45344 | `32feb6108156` (`DIRTY`) | 1.0.0 |
| C | admin-web / 15174 | 23956 | `32feb6108156` (`DIRTY`) | 0.1.0 |
| A | rag / 18000 | 37288 | `32feb6108156` (`DIRTY`) | OpenAPI 1.0.0 |

`DIRTY` 是验收运行工作树含本任务未提交修改时的真实值，已如实显示，而非伪称 `CLEAN`。

## 交接与限制

- 运行身份验证证明“浏览器实际加载的代码来自哪个工作目录/提交”，不等同于认证、授权、生产上线或真实客户数据许可。
- Page 身份只允许在已运行的 Vite 服务中读取；构建产物也包含同一 JSON，但生产部署仍应使用该部署工作目录重新构建和验收。
- A 的浏览器页签显示不在本任务授权范围内；A 的 Gate 身份只基于 API 入口与实际受管工作目录。
- 运行结束后须用现有安全停止脚本停止受管实例；Gate 不会按端口强杀未知 PID。
