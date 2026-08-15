# AI-CS 架构与 UI 闭环收敛 V1

日期：2026-08-15

Gate：`PASS / AI_CS_ARCHITECTURE_UI_CLOSURE_READY / SOURCE_ONLY`

本 Gate 只代表 AI-CS 源码和隔离 Synthetic/Replay 界面通过，不代表 Engine 自动授权、真实 PDD、自动发送、Pilot 或 Production Ready。

## 架构修复

- 风险问题集的多个 STORE/PRODUCT 扩展改为单调合并：风险和动作只取更严格值，必需事实、禁止声明和别名取并集，实时查询取 OR。后加载的较弱扩展不能覆盖先前更严格结论；同一 `question_id` 改写标准问法会以 422 拒绝。
- 单进程调试限流器会回收完整窗口外且无在途请求的键，避免长期运行后按“用户+店铺”积累无效桶；并发、分钟额度和异常释放语义不变。
- Admin Vite 代理支持通过 `VITE_PLATFORM_API_TARGET` 和 `VITE_AI_API_TARGET` 覆盖目标，默认 8011/8000 行为保持不变，允许并行验收使用独立端口。

## UI 修复

- 风险池增加一键清除筛选、可操作空状态、标准 tab/tablist/tabpanel 语义，以及更清晰但仍常驻的“不可用于生产/禁止自动发送”状态。
- 820px 以下全局侧栏默认折叠为品牌栏和菜单按钮；路由变化自动收起。顶部环境、服务、用户和退出操作重新分行，390px 宽度不再由侧栏占满首屏。
- 桌面端保持运营信息优先，技术哈希和依赖继续按需展开；知识编辑器既有分组和粘性保存栏无需结构性重做。

## 闭环证据

- A 全量：`239 passed, 3 skipped`；跳过项仍是显式 opt-in 的真实外部服务测试。
- C 全量：`216 passed`。
- Admin：最终 `38 files / 110 tests`，typecheck 与 production build 通过。
- C 生成的真实 36 题基线输入经 A 真实 `ReplyReadinessEvaluator + ReplyRouter` 完整执行：`36/36`。
- 隔离 C→A 真实 HTTP：`SYNTHETIC_C_TO_A_REAL_HTTP_OK`。
- 隔离可视化环境使用 19080/19081/15174、临时 SQLite 和独立 Edge Profile；真实 HTTP 风险池运行 `36/36`，结果为低风险 6、中风险 0、高风险 30；单条“你好”返回低风险直接回答且 `allow_auto_send=false`。
- Readiness/Router 候选 Schema 与 Fixture drift check、`git diff --check` 均通过。
- Contract 保持 `0.14.0 / coordinated`；Gateway raw SHA-256 `fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80`、canonical SHA-256 `e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5` 不变。

## 运行边界

- 未访问、迁移或重启正式数据库、向量库、DataRoot、PDD Profile、扫码窗口或正式候选端口。
- 未修改 Engine、CE、PDD、AutoPolicy、Sender、Receipt 或真实发送开关。
- 隔离界面只使用合成账号、商品、知识和临时数据库；关闭该验收环境不会影响正式候选。
