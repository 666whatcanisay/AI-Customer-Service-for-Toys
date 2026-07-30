# AI-CS 浏览器端到端验收

本目录保存可重复执行的产品级 Playwright 验收，不保存浏览器缓存、截图产物或业务数据。

- `customer/`：B 客服日常工作流；
- `admin/`：C 运营页面与导入中心回归；
- `workflows/`：跨页面业务闭环，目前包含 R009 商品知识导入。

运行示例：

```powershell
$env:AI_CS_B_URL='http://192.168.1.11:5173'
$env:AI_CS_ADMIN_URL='http://127.0.0.1:5179'
$env:R009_XLSX_PATH='C:\path\商品知识采集模板V1.xlsx'
$env:R009_EMPTY_XLSX_PATH='C:\path\admin_web\public\templates\商品知识采集模板V1.xlsx'
npm --prefix tests/e2e run test
```

R009 写入验收必须指向隔离 Admin，脚本会拒绝在 `5174` 上执行上传与审核。
