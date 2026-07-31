# BUG-B-001 — 单条不兼容店铺导致 B 全部商品目录不可用

- 等级：P1
- 模块：B 客服 / C 商品目录投影 / R006 兼容边界
- 状态：OPEN / R006_IMPLEMENTATION_PLAN_READY
- 发现时间：2026-07-30

## 问题描述

正式 C API `/api/v1/test-catalog/stores` 返回两个店铺：

- 汕明：`response_mode=SUGGESTION_ONLY`；
- 玩趣乐园积木店：`response_mode=HUMAN_CONFIRM_REQUIRED`。

B 的 `AiChat.loadStores()` 会查找任何不满足旧测试安全条件的店铺，只要发现一条就抛出契约错误并清空整个 `stores` 数组。因此浏览器顶部仍显示“平台可用”，但咨询区显示“数据服务不可用 / 商品目录暂不可用”，两个店铺都无法选择。

## 复现步骤

1. 打开正式 B：`http://192.168.1.11:5173/ai-chat`。
2. 等待商品目录加载。
3. 页面显示“数据服务不可用，请联系技术人员检查中台”和“商品目录暂不可用”。
4. 只读请求 `http://192.168.1.11:5173/platform-api/api/v1/test-catalog/stores` 返回 HTTP 200、两个店铺。
5. 检查 B `frontend/src/views/AiChat.vue` 的 `loadStores()`：`nextStores.find(...)` 找到任意不兼容店铺后抛错，catch 将 `stores=[]`。

## 影响

- B-001 正常咨询无法开始；
- B-003 商品资料不足、B-004 多 SKU、B-005 商品切换、B-006 连续对话均被阻塞；
- 单条数据问题扩大成全量 No data，属于主要日常流程异常；
- C 与 A 实际健康，页面“数据服务不可用”不能准确说明根因。

## 原因分析

当前正式 Runtime 仍使用 R006 实现前的测试目录契约。B 自行基于 `trial_enabled`、`test_data_mode`、`production_usable`、`response_mode` 和 `allow_auto_send` 判断整个 C 目录是否可信。这与已冻结的 R006 原则不一致：B 应只消费 C 的最终客服可用投影，单条异常不能导致全量 No data。

## 修复方案

本稳定性冲刺禁止修改 R006 边界，因此不能在 B 中增加新的可信度推断，也不能通过修改正式业务数据、删除店铺或篡改状态规避问题。

正确修复入口：在单独授权的 R006 Implementation 中由 C 提供最终客服可用投影，并按冻结规则隔离单条异常；B 仅消费投影。实施前仍需关闭 R006 V1.1 的映射和收据阻塞项。

不得采用的临时修复：

- B 静默过滤不兼容店铺；
- 把 `HUMAN_CONFIRM_REQUIRED` 直接当作自动可用；
- 修改数据库把店铺强制改为 `SUGGESTION_ONLY`；
- 删除玩趣乐园积木店；
- 用 Mock 或 API 直接调用代替浏览器咨询。

## 验证结果

尚未修复。正式 C/A 健康、B 页面和固定代理均 HTTP 200，但商品目录业务 Gate 为 FAIL。修复后必须重新执行 B-001、B-003～B-006，并验证单条异常不会清空其他可用店铺。
