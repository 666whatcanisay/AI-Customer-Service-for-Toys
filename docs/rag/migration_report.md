# RAG AI 客服独立化迁移报告

## 迁移范围

新项目位置：`C:\Users\EDY\Desktop\ai客服\rag-customer-service`

源项目保持在：`C:\Users\EDY\Desktop\ai客服\AI--master\源代码`

本轮采用复制方式，没有移动源文件。

## 复制和继承的内容

- 从 `AiChat.vue` 继承聊天消息、用户/AI 气泡、输入框、发送按钮、加载动画、空状态、推荐问题、服务状态和来源显示样式。
- 从 FastAPI 服务继承请求模型、健康/状态/统计/聊天能力。
- 从 `document_loader.py` 继承 PyMuPDF 普通文本 PDF 提取。
- 从 `vector_store.py` 继承 500 字切片、100 字重叠、标点优先、本地中文 Embedding、Chroma 持久化、`documents` 集合和 `distance` 字段。
- 从 `rag_service.py` 继承距离阈值、上下文构造、百炼兼容 OpenAI 客户端、Qwen 调用和来源结构。
- 复制三份原知识库 PDF 到 `backend/knowledge_base`。
- 复制原 Chroma 索引到 `backend/vector_db`。

## 修改的代码

- 增加集中配置 `app/config/settings.py`，所有目录从新项目 `backend` 解析。
- FastAPI 入口改为 `backend/app/main.py`，提供应用工厂以支持临时测试依赖。
- 新增统一接口和原 Java 代理兼容接口。
- Key 为空时不再构造失败的 OpenAI 客户端，也不输出堆栈给用户。
- 聊天命中后无 Key 时返回明确提示并保留来源。
- 增加直接检索和推荐问题接口。
- 前端移除 Pinia、登录、JWT、业务菜单和 Spring Boot 地址。
- 根路径及 `/chat`、`/ai-chat`、`/app` 均直接显示客服页面。
- Axios 改用 `VITE_API_BASE_URL`，开发请求由 Vite 转发至 FastAPI。
- 恢复客服页大模型配置入口，支持在本机配置、替换和清除百炼 Key，保存后无需重启。
- 配置接口限制为回环地址访问，Key 只原子写入 `backend/.env`，读取和保存响应均不回显明文。

## 移除的依赖

- Spring Boot、Maven、Java AI 代理。
- MySQL、Redis。
- 党建用户、角色、菜单、管理页面和业务 API。
- Pinia 用户 Store 和 JWT 拦截器。
- Python Jinja2 模板与独立静态聊天页，因为 Vue 页面是唯一前端入口。

## Java 代理结论

不保留。原代理仅做 HTTP 转发和响应包装，没有不可替代的参数转换、权限聚合或检索逻辑。兼容包装已迁至 FastAPI `/api/ai/*`。

## 配置与路径调整

- Key、模型、路径、阈值、Top K、Host 和 Port 均来自 `backend/.env`。
- 前端 API 前缀和代理目标来自 `frontend/.env`。
- 不存在指向源项目的运行时绝对路径。
- 新项目只操作自己的 `knowledge_base` 与 `vector_db`。

## 离线启动修复

默认开启 Hugging Face/Transformers 离线环境变量，并给 `SentenceTransformer` 传入 `local_files_only=True`。本地缓存存在时不访问外网；缓存不存在时立即返回明确错误。日志会说明从本地目录、本地缓存或在线仓库加载。

## 测试污染修复

没有复制原 `scripts/test_rag.py`。新 pytest 测试：

- 使用 pytest 临时目录。
- 使用独立 `test_documents` collection。
- 使用确定性测试 Embedding，不下载真实模型。
- 使用 `distance` 字段。
- 结束时关闭 Chroma 并清理临时目录。
- 不连接 `backend/vector_db`，更不会连接源项目索引。

## 原项目保护情况

- 未删除或移动源文件。
- 未运行源项目 `build_index.py`。
- 未修改源知识库。
- 未修改或清空源向量库。
- 未访问或修改原 MySQL 数据库。

最终验收会再次比较原 PDF 和 `chroma.sqlite3` 的 SHA-256。

## 当前遗留问题

- 只支持普通文本 PDF，无 OCR 和表格结构识别。
- 仍是单 collection，没有租户或知识库权限隔离。
- 全量重建，没有文档版本、哈希、增量更新和单文档删除。
- 没有多轮对话记忆。
- 拒答仍主要依赖向量距离阈值和提示词。
- 引用不能打开并高亮原 PDF。

## 后续升级建议

在独立项目稳定后，再按优先级增加：文档生命周期与去重、多知识库隔离、评测集和拒答校准、多格式解析/OCR、可追溯引用、多轮会话与运营管理后台。不要在这些基础治理完成前把项目标为生产级系统。

## 2026-07-21 实际验收结果

- `pytest -q`：11 passed，0 failed；测试 Chroma 和测试用 `.env` 均位于 pytest 临时目录。
- `npm run typecheck`：通过，0 个 TypeScript/Vue 类型错误。
- `npm run build`：通过，Vite 转换 1653 个模块并生成 `frontend/dist`。
- 一键启动：通过；8000 与 5173 正常监听。
- 停止后再次启动：通过；服务完整恢复。
- 离线加载：日志明确显示从 Hugging Face 本地缓存（离线模式）加载，没有网络重试记录。
- 知识库统计：3 份 PDF、55 个向量块、collection=`documents`。
- 无 Key 问答：服务保持就绪，返回明确提示和 2 条来源。
- 浏览器交互：根页面、输入、发送、加载、回答、来源文件/页码/距离/预览均正常，控制台无错误。
- 重建索引：停止服务后成功重建 22 页、55 个块；服务运行时会在删除前拒绝执行。
- 原 PDF SHA-256 与迁移前一致；原 `chroma.sqlite3` SHA-256 仍为 `84206102D5D323874547E69738F09B9E9D7BB5ECD295C67581AC5FCA455ADD5F`。

前端生产构建仅有 Element Plus 体积提示，不影响构建成功。pytest 仅有 FastAPI 0.104/Starlette TestClient 对 httpx 0.27 旧快捷方式的弃用警告，不影响 8 项测试通过。

## 验收期间额外修复

- PowerShell 5.1 会把无 BOM UTF-8 脚本中的中文字符串错误解码，因此运维脚本改为纯 ASCII 输出，避免解析失败。
- `npm install --prefix` 在当前 npm 调用方式下没有切换工作目录，已改为显式进入 `frontend` 后安装。
- Chroma 1.5 的测试 Embedding 协议需要 `embed_query`，测试替身改为继承官方 `EmbeddingFunction`。
- JSON 响应补充 `charset=utf-8`，修复 Windows PowerShell 5.1 查看中文状态时的乱码。
- 索引重建增加 HTTP 和 Python socket 双重运行检测；即使无权读取系统端口表，也会在删除任何文件之前拒绝重建。
- PID 停止失败时不再删除 PID 记录，并校验进程启动时间，降低 PID 重用导致误停的风险。
