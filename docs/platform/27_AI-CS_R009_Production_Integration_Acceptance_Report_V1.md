# AI-CS R009 Production Integration Acceptance Report V1

## 1. Gate结论

本轮完成了受控代码集成和生产数据结构兼容预检，但没有执行正式数据库迁移、标准Runtime切换或浏览器业务验收。

原因：浏览器自动化前置检查返回可用浏览器列表为空，无法满足真实页面点击、Excel上传、审核和截图的强制验收要求；同时，R008标准状态脚本把当前四服务运行身份判定为“不一致”（Git SHA与源码指纹一致，但runtimeMode不一致），不能在身份Gate未关闭时执行正式切换。按照Runtime Gate，不得用API、源码或单元测试冒充浏览器验收，也不得在强制验收能力或运行身份不满足时改动正式Runtime。

当前状态：`PRODUCT_KNOWLEDGE_IMPORT_PRODUCTION_BLOCKED_RUNTIME_AND_BROWSER_GATES`

## 2. 集成版本SHA

- 正式基线：`dd379278837a4f816dfb626292a26b0c54cce0cc`
- Feature：`feature/r009-product-knowledge-import-v1@4ab8f632b0edfe73433e88c5985f9e402bdd9874`
- 受控集成分支：`control/r009-production-integration-v1`
- 集成Merge SHA：`87a040c5806ec61e4e92dfe323aac752b4edef23`
- 集成Worktree：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-r009-production-integration-v1`

相对正式基线的变化根目录仅有 `platform_backend`、`admin_web`、`docs`。`backend`、`frontend`、`extension`、`contracts`、`scripts` 和 `admin_web/src/views/ImportCenterView.vue` 均无差异，R008启动能力保持不变。

## 3. 数据库迁移结果

正式数据库仍为 `0008_customer_feedback_loop_v1`，没有执行正式备份和正式迁移。

已使用SQLite在线只读备份能力，把正式库复制到集成Worktree的Git忽略预检区；仅在该副本执行：

```text
0008
→ upgrade 0009
→ alembic check
→ downgrade 0008
→ upgrade 0009
```

结果：最终revision为 `0009_product_knowledge_import_v1`，`PRAGMA integrity_check=ok`，三张R009表均存在。该文件是迁移兼容预检副本，不是正式切换前最终备份；正式备份必须在实际静默窗口、停止写入后重新生成。

## 4. 正式Runtime状态

- Repository：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`
- SHA：`dd379278837a4f816dfb626292a26b0c54cce0cc`
- 5173：继续运行B，实际监听 `192.168.1.11:5173`，直接HTTP为200
- 5174：继续运行未包含R009的Admin
- 8000：继续运行A
- 8011：继续运行C API，正式数据库仍为0008

本轮没有停止、重启或切换任何正式服务。

直接检查结果：C health、A `/api/health`、A `/api/status`、B LAN页面和Admin页面均为HTTP 200，A为 `ready=true`、`model_configured=true`。但以现存 `green-standard.local.ps1` 执行R008状态脚本时，四服务身份均显示“不一致”，细分证据为repositoryRoot、gitSha、sourceFingerprint均通过，runtimeMode失败；该配置同时把B健康地址记录为 `127.0.0.1:5173`，而B实际监听LAN地址，导致脚本显示B health不可用。正式切换前必须先冻结正确的标准/LAN运行配置并重新通过Runtime Identity Gate。

## 5. 浏览器自动化截图

无截图。浏览器运行时返回“无可用浏览器”，无法建立受控页面会话。没有使用HTTP 200、源码文本、API调用或测试截图替代真实浏览器证据。

恢复条件：提供一个可由Codex控制的内置Browser或Chrome扩展会话，再从5174页面入口重新执行完整浏览器验收。

## 6. Excel导入、Merge与审核结果

正式Runtime未执行Excel导入、Merge或审核，因此没有正式批次、正式审核收据或正式商品数据变化。

Feature隔离验收已有独立证据：真实Excel 19条、18个新增、1个既有，`ADD=202`、`UPDATE=1`、`KEEP=4`、`NO_CHANGE=2`，19张收据全部 `APPLIED`，批次 `COMPLETED`。这些结果只证明Feature能力，不能替代Production Browser Acceptance。

## 7. 异常测试结果

以下正式浏览器异常场景均未执行：

- 同一Excel重复上传的页面幂等体验。
- 修改Excel店铺名称后的整批阻断提示。
- 选择SKU差异模板后的“该模板导入功能暂未开放”弹窗。

后端和Admin单元测试已覆盖相关规则，但不作为Production Browser Acceptance通过证据。

## 8. 验证结果

- C Backend：101项pytest通过。
- Admin：25个文件、55项Vitest通过。
- Admin typecheck：通过。
- Admin production build：通过。
- 隔离正式库副本迁移往返和Alembic check：通过。
- Git差异边界：通过。

## 9. 发现问题与下一步

发布阻塞有两项：浏览器控制能力不可用，以及当前R008运行记录/配置与实际LAN运行模式不一致。恢复后必须重新执行：

1. 冻结正确的标准/LAN运行配置，令四服务Runtime Identity Gate通过。
2. 正式静默窗口与Runtime身份确认。
3. 停止正式写入并生成带SHA256、revision、完整性结果的最终数据库备份。
4. 正式数据库升级0009。
5. 将AI-CS正式目录切换到受控集成分支并启动四服务。
6. 验证5173/5174/8000/8011、R009四条路由和三步页面。
7. 用真实Excel完成页面上传、Merge、逐商品审核和商品知识更新。
8. 执行三项异常测试并保存截图。
9. 任一Gate失败时恢复 `dd379278` 和正式数据库备份。

不得在Runtime Identity Gate和浏览器Gate全部恢复前声明 `PRODUCT_KNOWLEDGE_IMPORT_PRODUCTION_ACCEPTED`。
