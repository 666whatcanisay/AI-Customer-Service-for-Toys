# 商品与 SKU 标准字段

固定列顺序如下，店铺不得改名：

| 字段 | 类型/约束 | 用途 |
|---|---|---|
| `tenant_id` | 必填，最长 64 | 租户隔离；单批次只允许一个租户 |
| `platform` | 必填枚举 | `douyin/taobao/pdd/jd/offline/other` |
| `store_code` | 必填，最长 128 | 店铺范围 |
| `product_code` | 可空，最长 128 | 与 `platform_product_id` 至少一个存在 |
| `platform_product_id` | 可空，最长 128 | 外部平台商品标识 |
| `product_name` | 必填，最长 255 | 已核实商品名 |
| `sku_code` | 可空，最长 128 | 与 `platform_sku_id` 至少一个存在 |
| `platform_sku_id` | 可空，最长 128 | 外部平台 SKU 标识 |
| `sku_name` | 必填，最长 255 | 已核实 SKU 名 |
| `specifications` | 可空，最长 2000 | 规范字符串；对象/数组 JSON 会稳定化 |
| `applicable_age_min/max` | 可空非负整数 | 适龄下限/上限 |
| `material` | 可空，最长 255 | 已核实材质 |
| `package_contents` | 可空，最长 2000 | 已核实包装内容 |
| `source_name` | 必填，最长 255 | 可追溯来源名称 |
| `effective_from/to` | 可空 ISO 日期 | 生效范围 |
| `notes` | 可空，最长 2000 | 导入备注；本轮不进入暂存实体 |

唯一判断使用规范化后的租户、平台、店铺、商品标识和 SKU 标识生成身份键，并用完整规范化行生成 SHA-256 `row_hash`。不会自动猜测缺失编码、年龄或平台。

`StagedProductSku` 预留 `external_system`、`external_product_id`、`external_sku_id`、`external_updated_at`；这些字段不作为内部主键。C-T02 只写 `external_system=MANUAL_EXCEL`。
