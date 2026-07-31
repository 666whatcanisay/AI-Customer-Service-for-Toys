# R006.1 Customer Enable Debug Report

> 检查日期：2026-07-31
>
> 检查类型：正式 Runtime 只读诊断
>
> 指定商品：`C-PRODUCT-0ff808af95ce419db9be49427f1c4813`
>
> 结论 Gate：`R006_1_CUSTOMER_ENABLE_DIAGNOSIS_COMPLETE`

## 1. 结论

指定商品不存在“批量启用没有写入”或“C投影没有进入B”的后端断点。正式数据库、Admin历史响应、C直连接口、B同源代理和B浏览器页面均证明该商品当前已经可供客服使用。

实际体验问题位于页面刷新与操作表达：

1. Admin“批量启用客服”按钮必须先勾选至少一个`APPROVED + DISABLED`商品；指定商品已经是`ENABLED`，因此不会再显示“选择批量启用”复选框。未选择其他待启用商品时，按钮显示“批量启用客服（0）”并禁用。
2. B商品目录保存在当前页面内存中。B只在页面初始化、店铺切换或人工点击“刷新商品目录”时读取C；没有轮询、WebSocket、SSE或目录失效通知。因此，启用动作发生前已经打开的B页面不会自动出现新商品，刷新目录或重新进入页面后才会显示。

链路真实状态为：

```text
Admin批量启用：成功
  ↓
C数据库：ENABLED + activation receipt
  ↓
C客服目录投影：包含指定商品
  ↓
5173 /platform-api代理：包含指定商品
  ↓
B新加载/人工刷新：商品可见、可选

B已经打开且未刷新：仍使用旧的内存商品列表
```

因此首个体验断点是“C投影已变化 → 已打开的B页面没有自动重新读取”，不是数据库、批量接口或C目录投影失败。

## 2. Runtime基线

| 项目 | 只读检查结果 |
| --- | --- |
| Repository | `C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS` |
| Branch | `release/r006-1-knowledge-activation-v1` |
| SHA | `98d62e67e8bdad663470c20d03f69bebb361a2e1` |
| Git | `CLEAN`（生成本报告前） |
| Runtime | `runtimeMode=standard`、`networkMode=LAN` |
| C API | 8011 RUNNING，监听`127.0.0.1` |
| B | 5173 RUNNING，监听`192.168.1.11` |
| Admin | 5174 RUNNING，仅本机 |
| Database | `0011_product_knowledge_publishing_v1` |

本轮未停止或重启任何服务。

## 3. 数据库真实状态

正式数据库：

`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS\.runtime\phase-e\data\standard-platform.sqlite3`

数据库使用SQLite只读URI打开，没有执行写事务。

### 3.1 商品

| 字段 | 实际值 |
| --- | --- |
| `product_id` | `C-PRODUCT-0ff808af95ce419db9be49427f1c4813` |
| 商品名称 | `(限量特价/袋装)机关山洞螺旋升降5机关/送2飞龙` |
| `review_status` | `APPROVED` |
| `customer_service_status` | `ENABLED` |
| 客服状态操作人 | `R006.1正式验收` |
| 客服状态更新时间 | `2026-07-31 05:56:28.038710` |
| `sales_status` | `OFF_SALE` |
| 旧字段`publishable` | `0` |
| SKU数量 | `0` |

`sales_status=OFF_SALE`和`publishable=0`是现存旧字段，但R006最终投影没有使用它们作为客服准入判断，B也没有读取或过滤它们。指定商品当前仍被C正式投影。若业务希望“下架商品不能进入客服”，应另行冻结状态规则，不能在本次诊断中直接改旧字段。

### 3.2 父店铺

| 字段 | 实际值 |
| --- | --- |
| 店铺 | `玩趣乐园积木店` |
| `store_code` | `c-store-6639df2982014226` |
| `data_source` | `PILOT` |
| `trial_enabled` | `true` |
| `customer_service_status` | `ENABLED` |

父店铺没有阻断商品投影。

### 3.3 AI知识发布

| 字段 | 实际值 |
| --- | --- |
| AI知识状态 | `PUBLISHED` |
| active collection | `test_knowledge_v031` |
| chunks / embeddings | `3 / 3` |
| current fingerprint | `539390be6469fc89d47f21e36a3ccc5ddacbc94803164a73a8ff851418ff3916` |
| indexed fingerprint | 与current一致 |
| publication receipt | `RAG-0b5a7648cd1fdb836678c9790c439e32` |
| last error | 无 |

### 3.4 激活状态与收据

| 字段 | 实际值 |
| --- | --- |
| Activation状态变化 | `DISABLED → ENABLED` |
| activation receipt | `ACT-5cc49873fd6e4d52a36f21ebefc96292` |
| source | `OPERATOR` |
| confirmed_by | `R006.1正式验收` |
| confirmed_at | `2026-07-31 05:56:28.038710` |
| confirmation_note | `运营已批量确认这些已审核商品可供客服人工选择使用` |

## 4. Admin批量启用检查

### 4.1 页面选择规则

`admin_web/src/views/KnowledgeCenterView.vue`只为以下商品显示“选择批量启用”复选框：

```text
data_status = APPROVED
AND customer_service_status = DISABLED
AND product_id存在
```

指定商品已经是`ENABLED`，因此页面正确地不再提供该商品的批量启用复选框。正式Admin浏览器只读检查结果：

- 目标店铺共有19个商品。
- 指定商品显示“资料：已通过 / 客服：已启用 / AI知识：已发布 / RAG chunks 3”。
- 另外18个`APPROVED + DISABLED`商品显示“选择批量启用”。
- 未选择时按钮为“批量启用客服（0）”且禁用。
- 仅在页面本地勾选1个待启用商品后，按钮变为“批量启用客服（1）”且可点击；随后已取消勾选。本轮没有提交POST。

这说明按钮本身不是失效，而是“批量启用”没有“自动全选”语义。

### 4.2 调用接口

Admin客户端调用：

```http
POST /api/v1/admin/operations/products/customer-service-status:batch
Idempotency-Key: batch-enable-<UUID>
Content-Type: application/json
```

请求结构：

```json
{
  "product_ids": ["<人工勾选的product_id>"],
  "confirmed_by": "<本次操作人>",
  "confirmation_note": "运营已批量确认这些已审核商品可供客服人工选择使用"
}
```

前端不会自动把当前店铺全部商品加入`product_ids`；只提交`selectedProductIds`。

### 4.3 指定商品历史返回结果

数据库中的批量幂等响应证明该请求已真实执行：

```json
{
  "result_status": "COMPLETE",
  "target_status": "ENABLED",
  "items": [
    {
      "product_id": "C-PRODUCT-0ff808af95ce419db9be49427f1c4813",
      "status": "CHANGED",
      "activation_receipt": {
        "activation_receipt_id": "ACT-5cc49873fd6e4d52a36f21ebefc96292",
        "previous_status": "DISABLED",
        "customer_service_status": "ENABLED"
      },
      "error_code": null,
      "message": "已启用客服使用"
    }
  ],
  "changed_count": 1,
  "unchanged_count": 0,
  "failed_count": 0
}
```

### 4.4 数据落点

| 事实 | 数据落点 |
| --- | --- |
| 商品最终客服状态 | `test_catalog_products.customer_service_status` |
| 操作人/时间 | `customer_service_status_updated_by / updated_at` |
| 状态变化审计 | `catalog_activation_receipts` |
| 单商品幂等响应 | `catalog_activation_idempotency`的`ITEM-*`记录 |
| 整批幂等响应 | `catalog_activation_idempotency`的`BATCH-*`记录 |

## 5. C投影与B读取结果

### 5.1 C直连接口

请求：

```http
GET http://127.0.0.1:8011/api/v1/customer-service/catalog/products
    ?store_code=c-store-6639df2982014226
```

结果：

- `schema_version=pilot-business-catalog.v1.1`
- `result_status=COMPLETE`
- `total=1`
- `warnings=[]`
- 指定商品存在
- `knowledge_status=APPROVED`
- `customer_service_status=ENABLED`
- `data_source=PILOT`

其他18个商品仍为`DISABLED`，因此没有进入客服最终投影。

### 5.2 B同源代理

B实际调用路径：

```http
GET /platform-api/api/v1/customer-service/catalog/stores
GET /platform-api/api/v1/customer-service/catalog/products?store_code=<store_code>
GET /platform-api/api/v1/customer-service/catalog/products/<product_id>/skus
```

通过`http://192.168.1.11:5173/platform-api/...`读取到的商品响应与C直连一致：`total=1`、指定商品存在、`customer_service_status=ENABLED`、无warning。

### 5.3 返回字段与过滤责任

C商品投影包含：

- `product_id`
- `platform`
- `store_code`
- 商品正式/显示名称
- `sales_status`
- `knowledge_status`
- `data_source`
- `customer_service_status=ENABLED`
- 年龄和安全摘要

Customer Available Catalog不包含activation receipt。收据是C Admin审计接口的事实，不是B目录选择所需字段；B另行读取的AI知识状态接口只包含publication receipt。

B没有根据`test_data_mode`、`production_usable`、`publishable`或`sales_status`再次判断可信度。B适配器只接受C最终投影中的`customer_service_status=ENABLED`记录，并隔离技术格式错误记录。

### 5.4 浏览器结果

正式B页面`http://192.168.1.11:5173/ai-chat`重新加载后：

- 自动选择`玩趣乐园积木店`。
- 商品下拉中存在指定商品。
- 该商品可以被实际选中。
- 页面显示“商品上下文已就绪”。
- AI知识显示“已发布”，引用数量3，发布收据已生成。
- SKU为空不会阻断使用；SKU在B中为可选项。

因此当前正式B不是“No data”，指定商品现在可以使用。

## 6. 同步断点

### 6.1 已通过的链路

| 层级 | 结果 |
| --- | --- |
| Admin批量请求 | `COMPLETE / CHANGED` |
| C数据库 | 商品和父店铺均`ENABLED` |
| Activation receipt | 存在且与商品、状态、操作人一致 |
| C目录投影 | 包含指定商品，`warnings=[]` |
| 5173代理 | 与C直连响应一致 |
| B适配器 | 接受该商品，没有二次业务过滤 |
| B新页面 | 商品可见、可选 |

### 6.2 实际缺口

`frontend/src/views/AiChat.vue`当前只在以下场景调用`refreshPlatform()`：

- `onMounted`页面首次进入。
- 用户点击“刷新商品目录”或技术详情中的“刷新”。
- 用户切换店铺后读取该店铺商品。

当前没有周期轮询、窗口重新聚焦刷新、SSE、WebSocket或其他C→B目录失效通知。Admin和B通常还是不同Origin、甚至不同电脑，不能依靠Admin页面本地状态自动更新B。

所以用户观察到的“启用后客服端还没有商品”是已打开B页面的旧内存列表，而不是批量启用失败。

## 7. 最小修复方案

### 7.1 立即可用的无代码处理

运营完成批量启用后，客服端执行以下任一操作：

1. 点击“刷新商品目录”；或
2. 重新加载B页面；或
3. 切换到其他店铺再切回目标店铺。

指定商品会出现，无需重复启用、修改数据库或重启服务。

### 7.2 最小代码修复建议（本轮未实施）

优先做B端目录自动失效刷新，不修改C数据模型、R006状态设计或接口契约：

1. B页面重新获得焦点或从隐藏变为可见时调用`refreshPlatform()`。
2. 可选增加仅在页面可见时运行的低频目录刷新；刷新后保留仍有效的店铺/商品选择，已被禁用的商品则清空并明确提示。
3. Admin批量成功文案增加“客服工作台将在刷新目录后可见”的操作提示。
4. Admin可增加“全选当前待启用商品”，但仍必须由运营明确勾选/确认，不能把批量按钮改成无确认的自动全启用。

这个方案只修复已有体验，不需要新增数据库字段、修改0011、改变B可信度判断或引入新的业务模块。

如果未来要求严格秒级实时同步，应单独冻结catalog version/ETag或SSE事件契约；不应在本次P2体验修复中直接引入新的跨线实时基础设施。

## 8. 本轮未执行事项

- 没有调用Admin启用/禁用写接口。
- 没有修改正式数据库或RAG。
- 没有修改代码、UI、contracts或Runtime配置。
- 没有停止或重启服务。
- 浏览器只执行店铺选择、商品选择和本地复选框勾选/取消；没有提交批量启用。

## 9. 最终判断

```text
数据库写入：PASS
Admin批量接口历史结果：PASS
C最终投影：PASS
B代理与适配：PASS
B新页面使用：PASS
已打开B页面自动感知Admin变化：MISSING
Admin批量按钮操作引导/全选能力：USABILITY_GAP
```

问题位置：`B页面目录刷新时机 + Admin批量选择交互表达`。

最小修复入口：先增加B窗口聚焦/可见性刷新和Admin成功提示；不要重构Customer Available Catalog。
