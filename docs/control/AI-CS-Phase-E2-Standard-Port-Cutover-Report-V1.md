# AI-CS Phase E2 Standard Port Cutover Report V1

> 文档类型：R008 标准端口运行迁移执行证据
>
> 执行日期：2026-07-30（Asia/Shanghai）
>
> 执行范围：Phase E2 — Standard Port Cutover Execution
>
> 最终结论：`RUNTIME_MIGRATION_COMPLETE`

## 1. 执行结论

Phase E2 通过。标准运行入口已经从 Recovery `cbc77ed...`切换到 Target `26f8cde...`；5173、5174、8000、8011 四个端口均由 Target 受管服务监听，运行记录、工作目录、Git SHA 与源码 clean 状态一致。

C revision 0008、A `ready=true`、`model_configured=true`和47 chunks均通过。B真实浏览器完成店铺/商品读取及一次合成测试问题的AI建议生成；Admin页面同时读取C与A，并验证运行时模块实际指向8011和8000。没有自动发送、退款、订单或其他自动业务动作。

Recovery四服务已按受管记录停止，但目录、Git、最终数据库备份、RAG资产和启动配置均保留，可作为回滚锚点。本轮没有触发回滚。

## 2. 切换身份与静默窗口

| 项目 | Recovery | Target |
| --- | --- | --- |
| Repository | `AI-CS-pilot-baseline-recovery-v1` | `AI-CS` |
| Branch | `control/pilot-baseline-recovery-v1` | `control/r008-physical-migration-v1` |
| SHA | `cbc77ed883cb99e2eff76ccb8eb3193bbddaba38` | `26f8cde1e8f7373315baa1ac68d02f7823b4de82` |
| Contracts | `0.2.0` | `0.2.0` |
| Git状态 | `CLEAN` | `CLEAN` |

人工静默窗口以本次明确执行授权为入口；执行前再次检查：

- 标准端口没有持续`ESTABLISHED`会话，仅有Recovery监听。
- Recovery SQLite在5秒观察窗口内保持733,184 bytes，LastWrite不变。
- 四服务health与运行身份均通过，Recovery与Target Git均clean。
- 切换期间只使用合成测试问题；没有采用、反馈、导入或运营写入。

## 3. 影子环境停止

使用Target官方停止脚本按`Admin → B → A → C API`停止影子服务：

| 影子服务 | 端口 | 停止前受管/监听PID | 结果 |
| --- | ---: | --- | --- |
| Admin | 15174 | 32404 / 30220 | STOPPED |
| B | 15173 | 42032 / 42032 | STOPPED |
| A | 18000 | 33680 / 35328 | STOPPED |
| C API | 18011 | 24096 / 24036 | STOPPED |

停止后四个影子端口均无监听，影子状态脚本显示四服务没有受管运行记录。

## 4. Recovery最终保护点

### 4.1 最终运行状态

停止前Recovery状态为：

| 服务 | 端口 | 受管PID | 监听PID | SHA/状态 |
| --- | ---: | ---: | ---: | --- |
| C API | 8011 | 19020 | 44428 | `cbc77ed...` / CLEAN / health PASS |
| A | 8000 | 20384 | 24844 | `cbc77ed...` / CLEAN / ready PASS |
| B | 5173 | 33360 | 33360 | `cbc77ed...` / CLEAN / page PASS |
| Admin | 5174 | 30732 | 38224 | `cbc77ed...` / CLEAN / page PASS |

四份受管记录及知识同步记录已复制到Target的Git忽略证据目录。随后按`Admin → B → A → C API`停止Recovery；未按端口强杀进程。

### 4.2 数据库保护

| 项目 | 结果 |
| --- | --- |
| Recovery源库 | `.runtime/data/pilot-baseline-recovery-platform.sqlite3` |
| 最终在线备份 | `.runtime/pilot-backups/platform-20260730-133209.sqlite3` |
| Target标准库 | `AI-CS/.runtime/phase-e/data/standard-platform.sqlite3` |
| 备份/Target预启动SHA-256 | `042d437acb0d3f183be42aafc74997fa781a7586295f7d42573d28d4e73b1dae`，一致 |
| SQLite完整性 | `ok` |
| Revision | `0008_customer_feedback_loop_v1` |
| 保护计数 | 店铺1、商品5、SKU18、FAQ16、安全规则8 |

源数据库物理文件SHA与SQLite online backup不同，是在线备份重写页面布局的既有现象；revision、完整性、全部表计数与Phase E1证据一致，备份与Target物化文件逐字节一致。

### 4.3 RAG保护

Recovery停止后将最终知识和向量资产复制到Target独立标准路径：

- 知识：1个文件、124 bytes；
- 向量：5个文件、1,038,500 bytes；
- 6个文件逐一Source/Target SHA-256一致；
- Target运行路径不引用Recovery可写目录。

## 5. 标准端口启动

使用Target官方启动脚本按`C API → A → B → Admin`启动。所有服务只绑定`127.0.0.1`。

| 服务 | 端口 | 受管PID | 监听PID | 工作目录 | 运行身份 |
| --- | ---: | ---: | ---: | --- | --- |
| C Platform API | 8011 | 21372 | 20424 | `AI-CS/platform_backend` | `26f8cde...` / CLEAN |
| A AI Service | 8000 | 27616 | 25528 | `AI-CS/backend` | `26f8cde...` / CLEAN |
| B Customer Client | 5173 | 13412 | 13412 | `AI-CS/frontend` | `26f8cde...` / CLEAN |
| C Admin Console | 5174 | 42400 | 6188 | `AI-CS/admin_web` | `26f8cde...` / CLEAN |

影子端口15173、15174、18000、18011保持释放；标准端口没有Recovery受管记录。

## 6. 后端与数据验证

| 验证项 | 结果 | 证据摘要 |
| --- | --- | --- |
| C health | PASS | 8011 `/health` HTTP 200，`status=ok` |
| C migration | PASS | revision `0008_customer_feedback_loop_v1` |
| C数据 | PASS | 店铺1、商品5、SKU18；SQLite `integrity_check=ok` |
| A health/status | PASS | `ready=true`、`model_configured=true`、无初始化错误 |
| A知识 | PASS | collection `documents`，47 chunks |
| Target源码 | PASS | Branch/SHA正确，Git clean |
| Contracts | PASS | `0.2.0`，未修改 |

Target运行日志没有Traceback、fatal、unhandled或error记录。

## 7. B客服工作台验证

真实浏览器打开`http://127.0.0.1:5173/ai-chat`并完成：

1. 页面显示AI可用、平台可用及人工确认安全边界。
2. 店铺1、商品5正常加载；选择一条测试商品后上下文就绪。
3. 输入不含客户信息的合成问题并点击“生成建议回复”。
4. 返回非空AI建议、风险提示和5条回答依据。
5. 页面继续显示`SUGGESTION_ONLY / AUTO_SEND_DISABLED`；没有点击采用、复制、反馈或案例保存。

验证后Target数据库仍为revision 0008、完整性`ok`，`ai_interaction_events=0`；本次只验证建议生成，没有形成反馈闭环写入。

## 8. Admin页面与实际路由验证

真实浏览器验证：

- `http://127.0.0.1:5174/overview`显示平台可用、AI可用及1/5/18目录计数。
- `/ai-capabilities`显示A已就绪、模型`qwen3.5:9b`和47条知识片段。
- 5174实际提供的Vite转换模块包含`VITE_AI_API_BASE_URL=http://127.0.0.1:8000`与`VITE_PLATFORM_API_BASE_URL=http://127.0.0.1:8011`，不包含18000/18011。
- 使用Admin Origin请求8000与8011只读health均返回HTTP 200，`Access-Control-Allow-Origin=http://127.0.0.1:5174`。
- B与Admin浏览器console均无error/warning，仅有Vite连接debug。

因此Admin的AI请求目标为8000，Platform请求目标为8011，不是只验证页面能打开，也没有残留影子端口路由。

## 9. 回滚与保护状态

本次没有触发回滚。当前回滚条件为：

1. 使用Target标准配置与受管记录按`Admin → B → A → C API`停止Target。
2. 确认5173、5174、8000、8011释放。
3. 从原Recovery目录和`config.local.ps1`按`C API → A → B → Admin`恢复。
4. 复核Recovery SHA、运行记录、C revision 0008、A 47 chunks和页面。

Recovery目录、Git提交、原数据库、最终在线备份、RAG源和依赖均未删除或修改。Target开始接受任何真实业务写入后，不得无条件回滚数据库；必须先备份并执行单独的数据协调。

## 10. 未执行事项

本轮没有：

- 修改代码、UI、contracts、requirements或lockfile；
- 修改数据库结构、重建/清空数据库；
- 修改A模型、Prompt或RAG逻辑；
- 执行R006或Business Data Activation；
- 删除Recovery、旧目录或Worktree；
- 开放LAN端口或处理R007网络问题。

## 11. 证据与下一入口

不进入Git的Target运行证据位于`.runtime/phase-e/`：

- `manifests/recovery-final-database-manifest.json`
- `manifests/recovery-final-rag-manifest.json`
- `manifests/standard-config-manifest.json`
- `manifests/standard-runtime-cutover-manifest.json`
- `manifests/recovery-final-runtime-records/`
- `green-standard/*.json`

标准运行切换manifest SHA-256：`064e7acab21b4e7958c76362a12d6c4233a470dc0731e0529e1f0a13689b4bce`。证据只记录路径、哈希、PID、状态和计数，不记录客户内容、知识正文或密钥。

R008仍为`IN_PROGRESS`，因为旧目录/Worktree退役尚未执行。下一阶段只能在单独授权后处理Phase F；在此之前必须持续保留Recovery回滚锚点。R006仍受IV11-B01/B02约束，本次切换不授权其Implementation。

最终状态：`RUNTIME_MIGRATION_COMPLETE`
