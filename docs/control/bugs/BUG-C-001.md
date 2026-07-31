# BUG-C-001：知识维护提交后缺少人工审核入口

- 等级：P1
- 模块：C Admin / 商品知识生命周期
- 状态：FIX_IN_PROGRESS
- 发现时间：2026-07-31
- 发现阶段：R006.1 Production Release V1 / Case 5

## 问题描述

“商品知识维护”可以生成 `RECOGNIZED` 待审核资料，但其“查看审核队列”入口仍指向
`/knowledge-materials`。R009 已将该路由冻结为“商品知识 Excel 导入与审核”，页面不再展示
通用知识资料的人工审核队列，因此运营无法通过 C Admin 完成已有知识维护闭环。

## 复现步骤

1. 打开 C Admin `/knowledge-editor`。
2. 选择店铺、商品，填写一项商品知识并提交。
3. 页面提示“已保存为待审核资料”。
4. 点击“查看审核队列”。
5. 实际进入 R009 Excel 导入页面，找不到刚提交的知识资料及审核操作。

## 原因分析

R009 为保持“资料上传与审核”三步 Excel 导入定位，替换了原
`KnowledgeMaterialsView`；原通用知识资料审核能力仍保留在 C API 和 Admin API client，
但没有迁移到独立路由。属于 UI 路由能力回归，不是 R009 Merge、R006 状态或 RAG 发布逻辑错误。

## 修复方案

- 新增独立 `/knowledge-review` 页面，只负责已有知识资料的列表、详情与人工审核。
- “商品知识维护”的审核队列入口改指向 `/knowledge-review`。
- 保持 `/knowledge-materials` 的 R009 Excel 导入定位和实现不变。
- 审核通过仍只允许资料进入受控质量分析；不会直接写入 R009 正式商品字段、发布 RAG、启用客服或修改 Prompt。

## 验证标准

- 运营可在浏览器中看到 `RECOGNIZED` 资料并执行审核通过/拒绝。
- 审核通过后资料进入 `APPROVED_FOR_ANALYSIS`，正式商品字段保持不变。
- R009 `/knowledge-materials` 页面、Import Center 和导入逻辑不变。
- Admin Vitest、typecheck、build 全部通过。
