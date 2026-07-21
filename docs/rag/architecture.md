# 架构说明

## 目标

本项目只负责把原业务系统中的 RAG 客服模块提取为可独立启动、运行和部署的原型，不重写检索算法，也不扩展为生产级知识库平台。

## 运行链路

```text
Vue AiChat.vue
  -> Axios（VITE_API_BASE_URL=/api）
  -> Vite Proxy（127.0.0.1:8000）
  -> FastAPI
  -> RAGService
     -> VectorStore
        -> BAAI/bge-small-zh-v1.5
        -> ChromaDB backend/vector_db
     -> Qwen（仅配置 Key 后）
  <- answer + sources[file/page/distance/content_preview]
```

## Java 代理决策

原 `AiController.java` 只完成以下工作：

1. 把 `/api/ai/status` 转发至 Python `/api/status`。
2. 把 `/api/ai/stats` 转发至 Python `/api/stats`。
3. 把 `/api/ai/chat` 的 `message` 原样转发至 Python `/api/chat`。
4. 将 Python 响应再包装为业务系统统一结果。

没有额外检索、权限聚合或不可替代业务逻辑，因此独立项目移除 Java、JWT、MySQL 和 Redis。必要的兼容响应由 FastAPI `/api/ai/*` 路由提供。

## 路径隔离

所有默认路径从 `backend` 目录解析：

- `./knowledge_base` -> 新项目 PDF 副本。
- `./vector_db` -> 新项目 Chroma 副本。
- `../logs` -> 新项目运行日志。

索引重建脚本要求目标路径位于新项目 `backend` 内且目录名为 `vector_db`，否则拒绝执行。

## 初始化与错误边界

FastAPI 进程先提供健康和状态接口，RAG 在后台线程加载。初始化失败时状态接口返回可读错误，聊天/检索返回 503；详细堆栈只进入本地日志。

未配置百炼 Key 不属于初始化失败。此时 `ready=true`、`model_configured=false`，本地检索和来源照常工作。

## 离线 Embedding

默认启用以下离线控制：

- `HF_HUB_OFFLINE=1`
- `TRANSFORMERS_OFFLINE=1`
- `HF_DATASETS_OFFLINE=1`
- `SentenceTransformer(..., local_files_only=True)`

这样本地缓存存在时不会先访问 Hugging Face，缓存不存在时也不会长时间重试。

## 非目标能力

OCR、多格式文档、表格识别、多租户、版本治理、增量索引、多轮记忆、高级拒答和后台知识库管理没有在本轮实现。
