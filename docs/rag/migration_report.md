# A-T02 源项目只读比较与选择性接入报告

## 审计边界

- 只读源：`C:\Users\EDY\Desktop\ai客服\rag-customer-service`。
- 正式工作区：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS-rag-core`。
- 访问原因：比较可复用 RAG 实现并确认本机依赖与模型能力。
- 访问结果：只读取源码、配置示例和虚拟环境包可用性；未修改源项目，未读取其 `.env`、知识文件、vector_db、日志或客户数据。
- 数据策略：没有迁移任何源数据；测试 PDF 在 pytest 临时目录中合成，Chroma 同样写入临时目录。

## 复用、适配与废弃

| 模块 | 决策 | A-T02 处理 |
|---|---|---|
| PyMuPDF 文本 PDF 解析 | 复用 | 保留 `DocumentLoader` 文字层逐页提取；仅用合成 PDF 验证 |
| 清洗和切分 | 适配 | 保留标点优先、重叠窗口；参数由 Settings 控制 |
| BGE Embedding | 复用 | 使用 `BAAI/bge-small-zh-v1.5`，离线本地缓存加载 |
| Chroma 持久化 | 适配 | 改用稳定 SHA-256 chunk ID 与 upsert；测试只写临时库 |
| Ollama/OpenAI 兼容 | 适配 | 新增 Ollama `/api/chat`；保留百炼兼容分支，默认 `qwen3.5:9b` |
| 检索、回答和引用 | 重写边界 | 先距离 Gate，再生成；统一 answer/action/source/model/latency/request_id |
| 源 frontend、真实知识、历史向量 | 废弃 | 不复制、不读取、不提交 |
| C 线审核、登录、金蝶、多租户 | 废弃 | 超出 A-T02 和 L1 范围 |

## 代码事实与验证结论

正式 A 线原有 PDF/BGE/Chroma 骨架，但缺少可导入的请求模型包，生成链路仍偏向百炼，引用字段不满足本任务。A-T02 补齐请求模型、Ollama 调用、稳定 chunk ID、受控拒答和完整响应字段，没有整体覆盖现有 A 线结构。

真实本地验证使用 Python 3.11.9、已存在的源项目虚拟环境、本地 BGE 缓存、临时 Chroma 和 Ollama `qwen3.5:9b`，完整结果为 `14 passed, 13 warnings in 13.52s`。相关问题命中合成 PDF 并回答 violet/紫色；火星税率问题拒答。该结果仅证明合成数据闭环，不代表生产知识、生产阈值或部署验收。
