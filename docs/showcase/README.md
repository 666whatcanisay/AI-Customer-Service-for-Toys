# AI-CS Public Showcase Assets

本目录只存放 GitHub 公开展示材料，不连接 AI-CS Runtime，也不读取数据库、向量库或真实业务接口。

## Demo 数据约束

- 店铺、商品、SKU、问题、回答、引用、状态、数量和收据均为虚构演示数据。
- 页面顶部统一显示 `DEMO DATA`，明确说明不连接真实业务系统。
- 不展示公司名称、真实店铺、真实商品、客户、订单、内网地址、数据库、集合名称或运行标识。
- `demo-ui.html` 是五张截图的可复现静态来源，不属于业务页面或 Runtime 入口。

## 展示资产

| 文件 | 内容 |
| --- | --- |
| `architecture.svg` | Excel 到 Customer Assistant 的公开架构图 |
| `images/01-customer-workbench.png` | AI 客服工作台 |
| `images/02-knowledge-center.png` | 运营知识中心 |
| `images/03-product-import.png` | 商品知识导入与 Merge |
| `images/04-ai-publishing.png` | AI 知识发布状态 |
| `images/05-rag-citations.png` | RAG 回答与来源引用 |

静态 Demo 页面支持参数：`customer`、`knowledge`、`import`、`publishing`、`rag`。截图由隔离浏览器对该静态页面全页渲染生成。
