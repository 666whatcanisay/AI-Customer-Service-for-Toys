# AI-CS R003 Browser Automation Recovery Report V1

## 1. 结论

R003 浏览器验收基础设施已恢复。新的验收入口由项目自身的 Playwright 1.62.0
直接启动隔离的系统 Chrome，不依赖 ChatGPT Chrome Extension、不复用用户 Default
Profile，也不要求修改 B 的 LAN 绑定、Runtime 配置或网络架构。

本轮仅执行非写入 Smoke。目标商品仍为 `DISABLED`，Customer Catalog 仍为 2，
目标 activation receipt 仍为 0。

状态：`AI_CS_R003_BROWSER_AUTOMATION_READY`

## 2. 原阻塞原因

- B 正式页面绑定 `192.168.1.11:5173`，`127.0.0.1:5173` 不监听。
- Chrome 扩展可以打开 LAN 页面，但无法稳定接管该页面 DOM；DOM Snapshot 超时。
- Windows 界面自动化无法可靠识别当前 Chrome URL，安全机制终止操作。
- AI-CS 四服务、数据库、Catalog、RAG 与模型均正常，问题只位于浏览器控制层。

## 3. 新方案

入口：`tests/e2e/workflows/r003-production-acceptance.cjs`

方案特征：

1. 复用 `tests/e2e` 已锁定的 `playwright 1.62.0`。
2. Playwright 捆绑 Chromium 缺失时，自动选择已安装的系统 Chrome：
   `C:\Program Files\Google\Chrome\Application\chrome.exe`。
3. 使用全新无用户数据 BrowserContext，不读取用户 Profile、Cookie 或扩展状态。
4. Admin 写入只允许由真实页面完成：选择店铺、勾选目标商品、填写操作人、
   接受人工确认对话框、点击批量启用。
5. Catalog、商品状态和 receipt 仅通过 GET 请求作前后验证，不使用 API 代替页面启用。
6. 默认 `smoke` 模式只读；`acceptance` 模式要求显式确认变量的值完全等于目标
   `product_id`，且商品必须处于 `APPROVED + PUBLISHED + DISABLED` 前置状态。
7. 证据写入 Git 忽略目录：
   `.runtime/phase-4-1/evidence/P41-R003-browser/`。

## 4. 修改文件

- `tests/e2e/workflows/r003-production-acceptance.cjs`
- `tests/e2e/package.json`
- `tests/e2e/README.md`
- `docs/control/AI-CS-R003-Browser-Automation-Recovery-Report-V1.md`

没有修改 `frontend/**`、`admin_web/**`、`backend/**`、`platform_backend/**`、
`contracts/**`、数据库、Runtime 或网络配置。

## 5. 非写入 Smoke 结果

执行命令：

```powershell
npm --prefix tests/e2e run test:r003:smoke
```

执行结果：`PASS_READ_ONLY`

### Admin

- `http://127.0.0.1:5174/knowledge-center`：打开成功。
- 店铺“玩趣乐园积木店”：唯一定位成功。
- 商品 `C-PRODUCT-747f463efb104440a6bdda416cd072eb`：唯一定位成功。
- 未勾选时批量启用按钮：disabled。
- 仅勾选目标商品后：按钮 enabled。
- 取消勾选后：按钮恢复 disabled。
- Admin 写请求：0。

### B Customer Workspace

- `http://192.168.1.11:5173/ai-chat`：打开成功。
- 店铺“玩趣乐园积木店”：可选择。
- 启用前可用商品：2。
- 目标商品启用前未出现在 B，符合 R006 设计。

### B → A 只读问答

使用一个已经在 Catalog 中的现有商品验证浏览器到 A 的真实链路：

- 问题：`这个商品适合多大年龄？`
- 请求：`POST /rag-api/api/chat`
- HTTP：200。
- `product_id`：`C-PRODUCT-0ff808af95ce419db9be49427f1c4813`。
- `sku_id`：`null`。
- 引用：3 条。
- Action：`🟡 建议确认`。
- Risk：`高风险`。
- 页面保留人工确认、不自动发送、不自动退款、不修改订单边界。

### 数据零变化复核

| 项目 | Smoke 前 | Smoke 后 |
| --- | ---: | ---: |
| 目标商品客服状态 | DISABLED | DISABLED |
| Catalog total | 2 | 2 |
| 目标 activation receipt | 0 | 0 |

## 6. 受控写入保护验证

未提供 `R003_ENABLE_CONFIRMATION` 时运行 acceptance，脚本在启动浏览器和执行任何写入前
以退出码 1 停止。保护 Gate 已验证通过。

正式验收入口：

```powershell
$env:R003_ENABLE_CONFIRMATION='C-PRODUCT-747f463efb104440a6bdda416cd072eb'
npm --prefix tests/e2e run test:r003:acceptance
```

脚本还会在执行前确认：

- Catalog 为 `COMPLETE`；
- 目标商品启用前不在 Catalog；
- 商品知识为 `APPROVED`；
- AI 知识为 `PUBLISHED`；
- 客服状态为 `DISABLED`；
- Admin 确认对话框明确显示只启用 1 个商品。

任一条件不满足立即失败，不进行补偿性 API 写入，也不会重复启用。

## 7. Quality Gate

| Gate | 结果 | 证据 |
| --- | --- | --- |
| Gate 1：稳定打开 Admin | PASS | 5174 页面和目标店铺加载成功 |
| Gate 2：定位目标商品 | PASS | 唯一 `data-testid` 定位成功 |
| Gate 3：读取按钮状态 | PASS | disabled → enabled → disabled，全程零写请求 |
| Gate 4：受控一次启用能力 | READY | 显式确认变量、前置状态和 Confirm Dialog 三重保护 |
| Gate 5：B/A 验证能力 | PASS | LAN B 页面、真实 A 请求、200、3 citations、安全边界 |

## 8. 证据

- `.runtime/phase-4-1/evidence/P41-R003-browser/R003-Browser-Automation-Smoke.json`
- `.runtime/phase-4-1/evidence/P41-R003-browser/R003-AUTO-Admin-Target-Selected.png`
- `.runtime/phase-4-1/evidence/P41-R003-browser/R003-AUTO-B-Before.png`
- `.runtime/phase-4-1/evidence/P41-R003-browser/R003-AUTO-B-AI-ReadOnly-Smoke.png`

## 9. 是否允许重新执行 R003

允许。下一步可以使用 `test:r003:acceptance` 完成唯一一次 Admin 启用、Catalog 2→3、
B 无硬刷新发现商品、目标商品三问、A 请求上下文与安全边界验证。

最终状态：`AI_CS_R003_BROWSER_AUTOMATION_READY`
