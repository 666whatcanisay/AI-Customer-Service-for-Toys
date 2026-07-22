# B-T03 店铺、商品和 SKU 选择式客服问答报告

## 结论

前端实现、类型检查、B-T03-FIX1 后 28 个测试和 production build 通过。真实 A/C 联调条件尚不具备，因此前端代码验收通过，真实页面 smoke 状态为 `INTEGRATION_PENDING`，不得用于真实客户。

## 页面流程

```text
C 店铺列表
→ 选择店铺（清空商品/SKU）
→ C 店铺商品
→ 选择商品（清空 SKU）
→ C 商品 SKU（可选）
→ 输入合成测试问题
→ A POST /api/chat
→ 校验响应 context 与选择一致
→ 展示回答、六种动作、风险、引用
→ 人工复制
→ 本页记录直接采用/修改后采用/未采用
```

SKU 留空时发送 `sku_id:null`。如果 A 返回 `ASK_CLARIFY`，页面显示“需要追问”和 required fields，不自动推断具体款式。

## 接口与兼容

- `VITE_RAG_API_BASE_URL` 默认 `http://127.0.0.1:8000`。
- `VITE_PLATFORM_API_BASE_URL` 默认 `http://127.0.0.1:8012`。
- C client 使用 `/health`、`/api/v1/test-catalog/stores`、`/api/v1/test-catalog/products?store_code=`、`/api/v1/test-catalog/products/{product_id}/skus`。
- C adapter 只接受顶层 `{items,total}` 及总控冻结字段。
- A 请求只发送 `{question,context}`；context 仅含 `tenant_id/platform/store_code/product_id/sku_id`。
- A chat adapter 只消费 `data`，不消费旧顶层镜像或旧 `ANSWER` 动作。
- 公共 `contracts/**` 未修改。

## 安全边界

页面持续显示“测试数据、仅供建议、禁止自动发送、不可用于真实客户”。固定试用值为 `TENANT-PDD-SM-TEST / pdd / PDD-SM`、`test_data_mode=true`、`production_usable=false`、`response_mode=SUGGESTION_ONLY`、`allow_auto_send=false`。生产代码没有 Mock 回退，也没有发送到电商平台的能力。

## 验证证据

- Node `v24.14.0`；npm `10.9.2`。
- `npm ci`：PASS；package/lock 无变化。
- `npm run typecheck`：PASS。
- `npm run test`：PASS，4 files、28/28 tests。
- `npm run build`：PASS，Vite 5.4.21。
- A health：可达，ready=true。
- A 冻结 chat 请求：HTTP 422，运行实例未升级。
- C health/catalog：`127.0.0.1:8012` 不可达。
- 真实页面 smoke：`INTEGRATION_PENDING`。

## 待联调清单

1. C 部署冻结的 stores/products/skus `{items,total}` 接口和测试目录。
2. A 接受 `{question,context}` 并在 `data.context` 回显相同范围。
3. 使用固定测试租户选择“拼多多→汕明→商品→SKU”，验证来源 `product_id/sku_id` 与选择一致。
4. 保持 `production_usable=false` 和 `allow_auto_send=false`；不得录入真实客户问题。

## B-T03-FIX1 路径修复

总控 Gate 发现初始 PR 使用了未冻结的 C 路径。FIX1 已删除旧路径，platform client 只调用三个 `test-catalog` 冻结路径，并新增 URL 精确断言测试。真实 A/C smoke 仍留待最终 develop 集成，没有以本地 Mock 冒充通过。

## 回滚

本任务只修改 `frontend/**` 与 `docs/customer/**`。回滚本任务提交即可恢复 B-T02 页面和文档，不涉及数据库、后端、共享契约或真实数据迁移。
