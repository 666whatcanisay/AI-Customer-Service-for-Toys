# BUG-QA-001 — B客服日常E2E仍按原生select操作

- 等级：P2
- 模块：QA / Playwright / B客服流程
- 状态：CLOSED
- 发现时间：2026-07-31
- 发现版本：`AI-CS@86a66cc`

## 问题描述

`tests/e2e/customer/daily-flow.cjs`通过`locator('option')`和`selectOption()`选择店铺、商品、SKU。正式B当前使用Element Plus `el-select`，真实页面虽然存在C投影的可用店铺与商品，测试仍立即失败为“没有可选择的业务选项”。

## 复现步骤

1. 保持正式B `192.168.1.11:5173`与C `8011`健康。
2. 使用Playwright Chrome运行`runCustomerDailyFlow()`。
3. 页面打开成功，但首个店铺选择在`selectFirstRealOption()`失败。

## 影响

- 产品客服目录未因此失效；R006正式只读目录为`COMPLETE + 2 stores`。
- 自动化不能覆盖B-001至B-005，会把测试驱动失配误判为业务无数据。

## 原因

E2E选择器停留在旧原生select实现，没有随当前Element Plus组件和本地工作台身份引导更新。

## 最小修复方案

- 为Element Plus选择器提供基于`data-testid`和可见下拉项的稳定操作器。
- 在隔离浏览器上下文设置符合`TESTER-*`规则的去标识化工作台身份。
- 保留正式只读运行与人工确认边界，不修改B API、页面业务逻辑或数据库。

## 验证要求

- 正式B完成店铺、商品与可选SKU选择。
- 年龄、材质、玩法真实问答和来源检查通过。
- 商品切换、多轮、无知识/不存在和高风险场景有明确证据。

## 修复与验证结果

- 增加Element Plus可见下拉项操作器，并在隔离浏览器上下文设置去标识化客服身份。
- 正式B `192.168.1.11:5173`完成店铺、商品选择；年龄、材质、玩法三问均返回非空建议。
- 三问分别返回3、2、3条引用；安全提示和风险标记持续存在。
- 另以正式目录完成商品A→商品B切换、商品B连续5轮上下文检查；所有A响应均保持目标`product_id`。
- 受控目录注入的不存在/无知识商品由真实A返回`REFUSE + KNOWLEDGE_NOT_PUBLISHED + 0 sources`，页面未暴露数据库/API技术错误。
- R006四态浏览器回归全部通过：`COMPLETE+items`、`COMPLETE+0`、`PARTIAL+items`、`PARTIAL+0`。

结论：测试驱动已与当前组件对齐，未修改B业务逻辑或正式数据。
