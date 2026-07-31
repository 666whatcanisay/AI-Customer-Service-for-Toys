# AI-CS R006.2 Customer Experience Polish Report V1

> 日期：2026-07-31
>
> 任务：R006.2 Customer Experience Polish V1
>
> 分支：`feature/r006-2-customer-experience-polish-v1`
>
> 正式Runtime基线：`98d62e67e8bdad663470c20d03f69bebb361a2e1` / `0011_product_knowledge_publishing_v1`
>
> 实现验收锚点：`a76ba1e13c34`
>
> 最终状态：`R006_2_EXPERIENCE_COMPLETE`

## 1. 结果

R006.2 已完成限定范围实现和隔离浏览器验收：C Admin 启用商品后，已经打开并停留在同一店铺的 B 客服页面不需要手动刷新浏览器；页面重新获得焦点时会读取 C 的最新 Customer Available Catalog，低频安全检查也会在页面可见期间每 60 秒执行一次。

本任务没有修改 R006 状态模型、R009、A、RAG、Prompt、contracts 或数据库结构，也没有切换正式 Runtime。

## 2. B 客服目录刷新

修改：

- 保留原有“刷新”和“刷新商品目录”人工入口。
- 页面重新获得焦点时读取最新 Store 投影和当前 Store 的 Product 投影。
- 页面可见期间每 60 秒执行一次低频检查；请求进行中不重复发起。
- 使用独立的后台请求控制器，不中断客服主动切换店铺、商品或 SKU 的请求。
- 当前 Store、Product 仍存在时保留商品、SKU 和已有咨询上下文。
- 当前 Store 或 Product 已被停用、移除时，清除失效的 Product、SKU、AI知识状态和旧回答，避免继续使用失效上下文。
- 页面卸载时移除 `focus` 监听、停止计时器并取消后台请求。

未引入 WebSocket、SSE、本地白名单或 B 侧可信度判断；B 仍只消费 C 最终投影。

## 3. C Admin 批量启用体验

商品知识中心已增加：

- 当前 Store 的“当前待启用”数量。
- “全选当前筛选结果”入口，只选择当前筛选中满足 `APPROVED + DISABLED` 且具有有效 Product ID 的商品。
- 批量启用前的人工确认。
- 启用成功后的明确提示：“客服工作台刷新目录后即可使用”。

全选只改变前端待提交选择，不会自动调用启用接口；运营仍必须填写操作人、点击批量启用并确认，C 后端继续生成 activation receipt。

## 4. 自动测试

| 模块 | 结果 |
| --- | --- |
| B 定向 `AiChat.spec.ts` | `38 passed` |
| B 全量 Vitest | `28 files / 119 passed` |
| B typecheck | PASS |
| B production build | PASS；保留既有大 chunk、Vite CJS 和 VueUse 注释警告 |
| Admin 定向 `KnowledgeCenterView.spec.ts` | `3 passed` |
| Admin 全量 Vitest | `27 files / 63 passed` |
| Admin typecheck | PASS |
| Admin production build | PASS |

新增回归覆盖：

- B 获得焦点后刷新目录并保留仍有效的 Product/SKU。
- B 60 秒低频检查在页面卸载后停止。
- Admin 待启用计数、当前筛选全选、人工确认和成功提示。

## 5. 隔离浏览器验收

### 5.1 环境

- C API：`127.0.0.1:18021`
- A：`127.0.0.1:18020`
- B：`127.0.0.1:15273`
- Admin：`127.0.0.1:15274`
- 代码：`a76ba1e13c34`
- 数据：正式 SQLite 的在线隔离快照
- 隔离 revision：`0011_product_knowledge_publishing_v1`
- 隔离数据库 `integrity_check`：`ok`

### 5.2 过程与证据

1. 先打开 B，选择“玩趣乐园积木店”，商品下拉初始只有 2 个 ENABLED 商品。
2. 保持该 B 页面打开，另开 Admin 商品知识中心。
3. Admin 选择同一店铺，页面显示“当前待启用：17 个”。
4. 勾选“只看待客服启用”和“全选当前筛选结果（17）”，填写隔离验收操作人。
5. 点击“批量启用客服（17）”并完成人工确认。
6. Admin 返回：成功 17、未变化 0、失败 0；页面提示“客服工作台刷新目录后即可使用”。
7. 回到此前已打开的 B 页面；未点击手动刷新、未重新加载浏览器。
8. B 页面获得焦点后，商品下拉自动更新为 19 个商品；新启用的“50盒【随机款式】科教机构优选”可见。

数据证据：

- 隔离库本次生成 17 条 activation receipt。
- 隔离 C 投影包含 19 个商品。
- 正式 C 投影仍为 2 个商品，证明浏览器验收没有写入正式数据库。
- 验收结束后 `15273/15274/18020/18021` 全部释放，正式 `5173/5174/8000/8011` 保持运行。

## 6. 变更边界

已修改：

- `frontend/src/views/AiChat.vue`
- `frontend/src/views/AiChat.spec.ts`
- `admin_web/src/views/KnowledgeCenterView.vue`
- `admin_web/tests/KnowledgeCenterView.spec.ts`
- R006.2 控制文档和上下文

未修改：

- `backend/**`
- `platform_backend/**`
- `contracts/**`
- R009 导入与 Import Center
- R006 状态和激活接口
- 数据库 migration

## 7. 剩余风险与发布入口

- 这是低频拉取，不是实时推送；页面保持焦点时最迟约 60 秒感知变化，切回页面时立即检查。
- 自动刷新失败时保留已有有效目录；契约错误或当前无目录时沿用现有可理解错误提示。
- 本轮完成的是实现和隔离验收，正式 Runtime 仍运行 `98d62e6`，尚未部署 R006.2。后续发布必须从本分支创建受控 Release，并重新执行 Runtime identity、四服务健康和正式只读 Smoke。

## 8. Gate

`R006_2_EXPERIENCE_COMPLETE`
