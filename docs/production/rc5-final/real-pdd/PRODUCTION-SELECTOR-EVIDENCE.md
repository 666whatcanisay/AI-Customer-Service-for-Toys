# Production Selector Evidence

当前状态：`BLOCKED — 等待本轮真实页面只读发现`。

不得从历史截图或旧代码猜测真实 Selector。Evidence 必须在用户手工登录并选中手机测试买家会话后，基于当前页面生成，至少记录：

- 官方页面 URL、页面 Fingerprint、Selector contract version；
- 店铺 ID/名称字段来源；
- 会话列表、活动会话、message ID、角色、正文、时间、序号；
- 商品、SKU、规格字段来源；
- Selector 匹配数量、iframe、虚拟列表和刷新稳定性；
- CUSTOMER/OPERATOR 真实样本；BOT/SYSTEM 未出现则 BLOCKED；
- 只读操作计数、写操作计数 0、发送计数 0；
- Evidence 生成时间、到期时间和 Hash。

验证前 `REAL_PDD_READ_READY` 必须保持 BLOCKED。

