# AI-CS Phase E1 Shadow Runtime Execution Report V1

> 文档类型：R008 运行迁移执行证据
>
> 执行日期：2026-07-30（Asia/Shanghai）
>
> 执行范围：Phase E1 — Green Shadow Runtime Execution
>
> 最终结论：`SHADOW_RUNTIME_PASS`
>
> 下一 Gate：`PHASE_E2_ENTRY_READY / STANDARD_PORT_CUTOVER_NOT_AUTHORIZED`

## 1. 执行结论

Phase E1 通过。Target 已在四个回环影子端口形成独立、可验证的运行环境；C、A、B、Admin 均来自同一 Target SHA，页面、API、模型、知识和业务只读投影均可用。Admin 的 AI 与 Platform 请求已经验证为实际指向 `18000/18011`，不是只打开页面，也没有回退到 Recovery 的 `8000/8011`。

Recovery 在整个执行期间持续运行。标准端口、受管/监听 PID、运行 SHA、SQLite 元数据和 RAG 源文件哈希均未变化。本轮未停止 Recovery、未切换标准端口、未修改代码/UI/contracts/数据库结构，也未执行 R006。

允许申请 Phase E2，但 E2 仍需用户单独授权和人工无写入窗口；执行入口必须先受管停止本次影子进程并确认影子端口释放，不得直接停止 Recovery。

## 2. 启动身份

### 2.1 Target

| 项目 | 结果 |
| --- | --- |
| Repository | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS` |
| Branch | `control/r008-physical-migration-v1` |
| HEAD | `26f8cde1e8f7373315baa1ac68d02f7823b4de82` |
| Tree | `9940eb270e340f6e47c325be28a57979e35c0c39` |
| Contracts | `0.2.0` |
| Git 状态 | `CLEAN`；`.runtime/phase-e/**`由现有忽略规则隔离 |

### 2.2 Recovery 保护锚点

| 项目 | 结果 |
| --- | --- |
| Repository | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-pilot-baseline-recovery-v1` |
| SHA | `cbc77ed883cb99e2eff76ccb8eb3193bbddaba38` |
| Git 状态 | `CLEAN` |
| 运行状态 | 四服务持续 `RUNNING`；未停止、未重启 |

## 3. 独立 Runtime 与数据路径

Target 独立运行根为：

```text
AI-CS/.runtime/phase-e/
├── config/
├── data/
├── rag/
│   ├── knowledge-base/
│   └── vector-db/
├── knowledge-materials/
├── green-shadow/
└── manifests/
```

| 资产 | Target 路径 | 保护结果 |
| --- | --- | --- |
| C SQLite | `.runtime/phase-e/data/shadow-platform.sqlite3` | 通过 SQLite online backup 形成；`integrity_check=ok`；revision `0008_customer_feedback_loop_v1` |
| A 知识目录 | `.runtime/phase-e/rag/knowledge-base` | 1 个文件、124 bytes；启动前与 Recovery manifest 一致 |
| A 向量目录 | `.runtime/phase-e/rag/vector-db` | 5 个文件、1,038,500 bytes；启动前与 Recovery manifest 一致 |
| C 资料存储 | `.runtime/phase-e/knowledge-materials` | 独立空目录；未引用 Recovery |
| 运行记录/日志 | `.runtime/phase-e/green-shadow` | 四服务受管记录独立；未写入 Recovery 运行目录 |

数据库快照 SHA-256 为 `042d437acb0d3f183be42aafc74997fa781a7586295f7d42573d28d4e73b1dae`。Recovery 主数据库持续为 733,184 bytes，LastWrite 仍为 `2026-07-29T15:32:41.2330435Z`，执行结束时哈希连续两次一致。

Target A 启动后只修改了 Target 自己的 Chroma/HNSW 运行副本；Recovery 的 5 个向量源文件仍与启动前 manifest 哈希完全一致。这一差异是独立可写路径生效的证据，不是 Recovery 数据被修改。

## 4. 启动顺序与 PID

按冻结顺序执行：`C API → A → B → Admin`。

| 服务 | 端口 | 受管 PID | 监听 PID | 工作目录 | SHA/源码状态 |
| --- | ---: | ---: | ---: | --- | --- |
| C Platform API | 18011 | 24096 | 24036 | `AI-CS/platform_backend` | `26f8cde...` / `CLEAN` |
| A AI Service | 18000 | 33680 | 35328 | `AI-CS/backend` | `26f8cde...` / `CLEAN` |
| B Customer Client | 15173 | 42032 | 42032 | `AI-CS/frontend` | `26f8cde...` / `CLEAN` |
| C Admin Console | 15174 | 32404 | 30220 | `AI-CS/admin_web` | `26f8cde...` / `CLEAN` |

四个服务均绑定 `127.0.0.1`，没有开启 LAN 暴露。

## 5. API 验证

| 验证项 | 结果 | 证据摘要 |
| --- | --- | --- |
| C health | PASS | `GET http://127.0.0.1:18011/health` → HTTP 200，`service=platform-backend` |
| C migration | PASS | revision `0008_customer_feedback_loop_v1` |
| A health | PASS | `GET http://127.0.0.1:18000/api/health` → HTTP 200 |
| A status | PASS | `ready=true`、`model_configured=true`、`initialization_error=null` |
| A 知识 | PASS | collection `documents`，`chunk_count=47` |
| A 模型调用 | PASS | 启动真实 smoke 后调用 1 次、成功 1 次、异常 0 次 |
| B root | PASS | `GET http://127.0.0.1:15173/` → HTTP 200 |
| Admin root | PASS | `GET http://127.0.0.1:15174/` → HTTP 200 |

## 6. 页面验证

### 6.1 B 客服工作台

真实浏览器验证通过：

- 首页显示“AI 可用”“平台可用”。
- `/ai-chat` 正常渲染商品上下文、问题输入和人工确认流程。
- 影子快照中的旧测试业务数据可读取：店铺 1、商品 5、SKU 18。
- 页面继续明确“禁止自动发送、禁止自动退款、禁止修改订单”。
- 浏览器 console error/warning 均为 0。

### 6.2 C Admin

真实浏览器验证通过：

- 运营首页显示“平台可用”“AI 可用”。
- 业务概览显示店铺 1、商品 5、SKU 18。
- `/ai-capabilities` 显示 AI 服务已就绪、模型 `qwen3.5:9b`、47 条可查询知识片段。
- 本次启动后的模型观察显示调用 1、成功 1、异常 0。
- 浏览器 console error/warning 均为 0。

## 7. Admin 实际请求路由验证

本项没有使用“页面能打开”作为通过条件，证据链如下：

1. `15174` 实际提供的 Vite 转换模块 `/src/api/client.ts` 返回 HTTP 200，并注入：
   - `VITE_GIT_SHORT_SHA=26f8cde`
   - `VITE_AI_API_BASE_URL=http://127.0.0.1:18000`
   - `VITE_PLATFORM_API_BASE_URL=http://127.0.0.1:18011`
2. 该运行时模块不包含 `http://127.0.0.1:8000` 或 `http://127.0.0.1:8011`。
3. Admin 应用挂载时实际调用 `getHealth()` 与 `getAiControlCenterOverview()`；页面结果分别显示 Platform 与 AI 可用。
4. 使用 Admin Origin `http://127.0.0.1:15174`直接验证实际目标：
   - `GET http://127.0.0.1:18011/api/v1/admin/overview` → HTTP 200，CORS Origin 正确，返回 1/5/18 计数。
   - `GET http://127.0.0.1:18000/api/admin/ai/control-center/overview` → HTTP 200，CORS Origin 正确，`RUNNING/ready=true/model_configured=true`，47 chunks。

结论：Admin 的 Platform 请求实际到 `18011`，AI 请求实际到 `18000`；不存在用 Recovery 标准端口伪装 Green 通过的情况。

## 8. Recovery 与标准端口保护

执行结束时标准端口仍由原 Recovery 监听 PID 占用：

| 服务 | 标准端口 | Recovery 监听 PID | SHA |
| --- | ---: | ---: | --- |
| B | 5173 | 33360 | `cbc77ed...` |
| Admin | 5174 | 38224 | `cbc77ed...` |
| A | 8000 | 24844 | `cbc77ed...` |
| C API | 8011 | 44428 | `cbc77ed...` |

Recovery 官方状态检查再次确认四服务 `RUNNING`、运行身份已验证、源码 `CLEAN`、C revision 0008、A 47 chunks `MATCH`、模型 ready。

## 9. 禁止项与回滚情况

本轮未执行：

- 停止或重启 Recovery；
- 占用或切换 `5173/5174/8000/8011`；
- 修改代码、UI、contracts、requirements、lockfile；
- 修改数据库结构或清空业务数据；
- 修改模型、Prompt、RAG 逻辑；
- 执行 R006 Business Data Activation；
- 处理旧目录或 Worktree。

没有触发失败回滚。Recovery 从未退出运行，因此回滚锚点始终可用。影子四服务在本报告完成时保持运行，供后续受管停止与 E2 前置复核；不得按端口强杀。

## 10. Phase E2 入口判定

判定：允许申请进入 Phase E2，状态为：

```text
SHADOW_RUNTIME_PASS
PHASE_E2_ENTRY_READY
STANDARD_PORT_CUTOVER_NOT_AUTHORIZED
RECOVERY_RUNTIME_UNCHANGED
```

Phase E2 的强制前置条件：

1. 用户单独授权标准端口切换和人工无写入窗口。
2. 使用本次 Target 受管记录停止四个影子服务，并确认 `15173/15174/18000/18011` 释放。
3. 再次确认 Recovery `cbc77ed...`、四个标准端口 PID、SQLite/RAG 锚点和最终备份。
4. 只使用官方受管脚本停止 Recovery；禁止按端口强杀。
5. 标准端口启动后重新验证 PID/目录/SHA、C 数据、A 模型与 47 chunks、B/C 页面及 Admin 实际路由。
6. 任一 Gate 失败立即停止 Target，并从原 Recovery 配置恢复；仍不得实施 R006。

## 11. 证据位置

不进入 Git 的运行证据位于 Target：

- `.runtime/phase-e/manifests/database-snapshot-manifest.json`
- `.runtime/phase-e/manifests/rag-snapshot-manifest.json`
- `.runtime/phase-e/manifests/shadow-config-manifest.json`
- `.runtime/phase-e/manifests/shadow-runtime-execution-manifest.json`
- `.runtime/phase-e/green-shadow/*.json`

运行执行 manifest SHA-256：`acb773d526ff54c67f1d7465b392df357e4eef45d297b35138cff49835d85152`。上述文件仅记录路径、哈希、PID、状态和计数，不记录客户内容、知识正文或密钥。

最终状态：`SHADOW_RUNTIME_PASS`
