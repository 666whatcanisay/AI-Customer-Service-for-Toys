# API 说明

接口属于 C 线本地 `/api/v1`，未修改共享 `contracts/**`：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/import-templates/product-sku` | 下载固定 XLSX 模板 |
| POST | `/api/v1/import-batches/product-sku` | multipart 上传；字段 `file`、可选 `created_by` |
| GET | `/api/v1/import-batches` | `page/page_size` 分页列出批次 |
| GET | `/api/v1/import-batches/{batch_id}` | 批次摘要及 `staged_rows` |
| GET | `/api/v1/import-batches/{batch_id}/rows` | `status/page/page_size`；状态为 VALID/INVALID/DUPLICATE/CONFLICT |
| GET | `/api/v1/import-batches/{batch_id}/errors` | UTF-8 BOM CSV 行级错误报告 |

上传成功为 HTTP 201，返回 `id` 与同值 `batch_id`、状态、总行、有效行、错误/冲突行和重复行。文件级错误使用统一结构：

```json
{
  "error": {"code": "UNSUPPORTED_FILE_TYPE", "message": "..."},
  "request_id": "..."
}
```

行列表与错误 CSV 提供完整行号、字段、原始值和修改建议。批次删除、审核、发布、金蝶同步、电商同步和 A 线发布接口均未建立。

未来 B 线线索提交草案只能传递本页标准字段及来源上下文，C 线仍需校验并写入待审核区；任何跨线正式接口必须另行执行 schema、版本、CHANGELOG、兼容性说明与受影响线路审查。
