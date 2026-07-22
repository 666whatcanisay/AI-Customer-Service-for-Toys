# XLSX 导入前预检

C-T02A 在正式导入前提供只检查、不入库的质量预览：

```text
POST /api/v1/import-batches/product-sku/preflight
Content-Type: multipart/form-data
file=<xlsx>
```

## 返回字段

- `original_filename`：移除路径后的安全 basename；
- `file_sha256`、`file_size_bytes`：本次请求字节的指纹与大小；
- `worksheets`、`data_row_count`：工作表列表与非空数据行数；
- `missing_columns`、`unknown_columns`：相对固定 18 列模板的差异；
- `formula_cell_count`、`hidden_sheet_warnings`、`blank_row_count`；
- `valid_rows`、`invalid_rows`、`duplicate_rows`、`conflict_rows`；
- `error_summary`、`warning_summary`：按 code 聚合的数量和说明；
- `can_import`：是否允许管理端进入正式上传操作。

## 判定

缺表、缺列、未知列、列顺序错误、隐藏数据表、无数据、行数超限、公式、字段校验错误、重复或冲突都是阻断错误，`can_import=false`。隐藏的非数据工作表和被忽略的空白行作为警告，不单独阻断导入。

管理端必须在当前所选文件预检通过后才能启用正式上传；重新选择文件会清除旧结果。`can_import` 不是服务端信任凭证，正式上传接口仍独立重复文件安全、解析、标准化、校验、重复和冲突判断，以保持 C-T02 兼容性。

## 零写入边界

预检路由不依赖 `get_db`，服务使用无 repository 的只读路径；不创建 `ImportBatch`、`ImportRow`、`StagedProductSku`，不保存工作簿或结果，也不需要数据库迁移。本轮没有新增 Alembic revision。

预检不是恶意文件扫描、权限、审计持久化或生产安全认证；只允许人工构造测试数据，未接 A/B、金蝶、RAG、Chroma 或真实公司资料。
