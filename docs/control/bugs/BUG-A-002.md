# BUG-A-002：不存在商品命中其他商品知识

- 等级：P1
- 模块：A AI 能力层 / RAG 范围隔离
- 状态：`FIXED_VERIFIED`
- 发现版本：`AI-CS@4edf131cb341993b12a0143b0388d932b29faf84`
- 修复提交：`18a20f70ec5cd4c4da7baef0179cc30db0dbff5a`
- 正式验证版本：`AI-CS@42bafcf6630ccbcd1c2dd1d55cb7d3fe735cb1e2`

## 问题描述

传入不存在的 `product_id=PDD-SM-P9999` 时，A 返回 6 条其他商品/店铺来源，存在跨商品回答风险。

## 复现步骤

1. 使用冻结 tenant/platform/store 和不存在的 product_id 请求 `/api/chat`。
2. 提问“这个不存在的商品有什么功能？”。
3. 检查 action、sources 及每个来源的 product_id。

## 原因分析

目标商品零命中后，检索回退仍允许店铺级运营知识进入普通商品事实回答，导致范围扩大。

## 修复方案

非店铺级安全/运营意图必须至少存在目标商品证据；普通问题不能用其他商品或宽范围店铺知识补齐。高风险店铺安全规则仍可用于人工转接保护。

## 验证结果

- 不存在商品：`REFUSE`、sources=0。
- 商品资料不足：`REFUSE`、sources=0。
- 商品切换：P0003/P0005 的来源均只属于当前 product_id。
- 多 SKU：Q65、Q66、Q66-RGB6 均只返回当前 product_id 和 sku_id 的来源。
- A 全量：`105 passed, 3 skipped`。
