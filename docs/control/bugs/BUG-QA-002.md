# BUG-QA-002 — R009浏览器测试未等待异步Merge预览

- 等级：P2
- 模块：QA / Playwright / R009
- 状态：CLOSED
- 发现时间：2026-07-31
- 发现版本：`AI-CS@86a66cc`

## 问题描述

R009页面在上传POST返回后继续并行读取preflight和merge-preview。现有E2E只调用`waitForLoadState('networkidle')`；页面早已完成初始加载时，该调用可立即返回，导致测试在预览DOM渲染前断言`UPDATE/KEEP/NO_CHANGE`。

## 真实证据

- 隔离数据库批次已真实生成`UPDATE=1、KEEP=5、NO_CHANGE=203`。
- 重新打开同一批次时页面正确展示“更新”“保留原值”“无变化”。
- 正式数据库和R009代码未被修改。

## 最小修复

上传动作同时等待POST、preflight GET和merge-preview GET三项响应，再检查页面结果；不修改R009页面或接口。

## 验证要求

- 全新隔离库完成ADD后审核。
- 更新工作簿稳定显示UPDATE/KEEP/NO_CHANGE并审核。
- 重复、错误店铺、空模板、缺商品名称、未开放模板全部通过。

## 验证结果

- 隔离数据库从空库迁移至`0012_internal_production_finalization_v1`。
- 真实四Sheet工作簿识别19条商品；首次导入产生`ADD=205、KEEP=4`并审核19项。
- 更新工作簿产生`UPDATE=1、KEEP=5、NO_CHANGE=203`并审核1项。
- 重复上传显示无待审核变化；错误店铺、空工作簿、缺商品名称整批阻断；未开放模板提示正确。
- 该问题仅涉及QA等待时序，未修改R009业务实现。
