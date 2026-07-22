# A-T01 导入 RAG 基线静态审查

## 审查性质

- 审查日期：2026-07-21
- 审查基线：`ddb6bad feat(skills): complete shared agent skill baseline (#2)`
- 分支：`agent/rag-core`
- 范围：静态读取 `backend/**`、启动脚本和 A 线文档。
- 结论：A-T01 的静态审查和受阻基线已形成；运行测试仍为 BLOCKED，A-G1 尚未通过。

本轮没有安装依赖、没有启动前后端服务、没有调用真实模型、没有读取 Desktop 历史备份或真实 PDF、没有创建或读取真实向量数据库，也没有运行索引重建。

## 源码可证实的当前结构

| 环节 | 源码事实 | 证据边界 |
| --- | --- | --- |
| 前端请求 | Axios 默认以 `/api` 为基址。 | 仅静态确认，未启动前端。 |
| FastAPI 路由 | 当前包含 health、status、statistics、recommended questions、retrieval search、chat、model config 和 `/ai/*` 兼容路由。 | 当前实际接口不是计划中的 `/api/chat/assist`。 |
| RAG 编排 | `RAGService.query` 调用检索、阈值判断、上下文构建和 LLM 调用。 | 未进行运行验证。 |
| 检索与索引 | `VectorStore` 使用 Chroma PersistentClient；默认 500 字切片、100 字重叠、余弦距离阈值 0.6、Top-K 2。 | 当前没有 `backend/vector_db`。 |
| 文档读取 | `DocumentLoader` 仅扫描并提取普通文本 PDF。 | 当前 `knowledge_base` 只有 README，没有真实 PDF。 |
| 模型 | 当前代码使用 DashScope OpenAI-compatible client，默认 `qwen-turbo`。 | 没有 Ollama 客户端或 Qwen3.5 9B 运行证据。 |
| Embedding | 默认 `BAAI/bge-small-zh-v1.5`，离线模式使用 `local_files_only=True`。 | 缓存与模型均未在本轮加载。 |

## 运行与测试阻塞

- 可用隔离 Python 为 3.12.13，`backend/.venv/Scripts/python.exe` 不存在。
- 当前环境缺少 pytest、FastAPI、Uvicorn、ChromaDB、sentence-transformers、PyMuPDF 和 OpenAI Python 依赖。
- 已尝试 `python -m pytest -q backend/tests`；命令在测试收集前以 `No module named pytest` 结束。因此 pytest 未运行，不能写成通过。
- FastAPI、Embedding、Chroma、真实模型、前后端连通和真实问答均未运行或验收。

## 计划能力与当前能力的边界

计划书中的 Ollama/Qwen3.5 9B、`/api/chat/assist`、统一安全动作、文档版本、增量索引、单文档删除、多格式解析和租户隔离均为计划能力，不是当前已验证能力。旧迁移报告所述“3 份 PDF、55 个向量块、启动通过、索引重建通过”与当前工作区不一致，不能作为当前运行证据。

## 数据排除与回滚

- 真实知识文件、vector_db、模型、密钥、日志、数据库和客户数据不属于提交范围。
- 本交付仅修改 `docs/rag/**`；回滚可还原对应文档提交，不影响业务代码或本地数据。
- 下一建议任务可以记录为 A-T02，但不得把它写成当前任务或在本轮执行。
