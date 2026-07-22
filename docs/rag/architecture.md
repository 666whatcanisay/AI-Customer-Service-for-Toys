# 架构说明

## 运行链路

```text
API Client -> FastAPI Route -> RAGService -> VectorStore
                                      |        |-> BGE Embedding
                                      |        `-> Chroma
                                      `-> Ollama qwen3.5:9b
<- answer/action/sources/model/latency_ms/request_id
```

PDF 由 PyMuPDF 提取文字层，按标点优先策略进行重叠切分。每个 chunk 使用内容相关 SHA-256 ID 并通过 Chroma `upsert` 写入。检索先进行距离 Gate；未通过时直接拒答，不调用模型。

## 初始化与数据隔离

FastAPI 在后台线程初始化 RAG。启动阶段只打开 collection 并在已有向量时执行一次预热查询，不自动解析 PDF、下载模型或重建索引。空 collection 可正常初始化，检索返回空结果。

A-T02 测试的 PDF、知识目录、Chroma 和日志均位于 pytest 临时目录。仓库默认路径保留用于后续正式运行，但本轮没有创建、读取或提交真实知识库与 `backend/vector_db`。

## 非目标能力

OCR、复杂表格、多租户、文档审核、版本生命周期、增量索引、多轮记忆、生产阈值校准和 A-T03 均不在本轮实现范围。
