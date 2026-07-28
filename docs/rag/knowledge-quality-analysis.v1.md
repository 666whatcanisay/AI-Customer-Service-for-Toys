# 商品资料质量分析（A 线，V1）

## 用途与边界

这是一个需要运营人员显式触发的分析桥接：A 只从 C 读取已经人工审核、去标识化且不可变的商品资料快照，调用已配置的本机 `qwen3.5:9b`，再把结构化的中文缺口建议写回 C。

它不轮询、不自动运行，也不会发布知识到 RAG、改写 Prompt、训练或更新模型、发送客户消息，或执行订单、退款、售后与 ERP 动作。C 始终是资料、审核状态、修订版本和分析结果的唯一事实来源。

原始上传文件、审核后的资料正文和模型提示词只在一次运行的内存中使用：A 不把它们写入日志、数据库、响应或 Git。

## 受控入口

`POST /api/admin/ai/knowledge-quality/run`

请求仅接受：

```json
{"maximum": 1}
```

- `maximum` 为 1 到 20，默认 1；每次运行都由人工发起。
- 该入口只允许本机回环请求。运营页面如需触发，应通过服务器本机的受控调用路径，而不是把 A 管理接口暴露给局域网用户。
- 响应只返回资料 ID、revision、`analysis_run_id`、模型和 Prompt 版本、缺口数量和 C 的写回状态；不返回资料正文、识别摘要或模型 Prompt。

## 已冻结的 C 交互

读取：

```text
GET /api/v1/admin/knowledge-quality/analysis-inputs?material_status=APPROVED_FOR_ANALYSIS&page=&size=
```

写回：

```text
POST /api/v1/admin/knowledge-quality/analysis-results
```

A 只接受 `material_id`、`revision`、`content_hash` 精确匹配的 C 快照。审核后 `analysis_text` 可包含正常 LF/CRLF 分行，A 在内存中规范为 LF；其上限与 C 对齐为 24,000 个字符，裸回车和其他不可打印控制字符会被拒绝。模型输出必须是中文、受长度限制的 JSON：

```json
{
  "summary": "面向运营的中文资料质量概括",
  "gaps": [
    {
      "gap_code": "MISSING_PACKAGE_CONTENTS",
      "severity": "MEDIUM",
      "title": "缺少包装清单",
      "description": "中文缺口说明",
      "recommended_action": "仅供人工执行的中文补充建议"
    }
  ]
}
```

不合格的模型输出不会写回 C，也不会生成替代或模拟结果。

## 配置

运行环境必须显式提供：

```text
PLATFORM_API_BASE_URL=http://127.0.0.1:8011
PLATFORM_API_TIMEOUT_SECONDS=30
LLM_PROVIDER=ollama
LLM_MODEL=qwen3.5:9b
LLM_BASE_URL=http://127.0.0.1:11434
KNOWLEDGE_QUALITY_PROMPT_VERSION=knowledge-quality.v1
```

写回成功需由 C 返回同一 `analysis_run_id` 和 `overall_status=ANALYZED`；C 自行生成 `assessment_id`、`gap_id` 和各 gap 的初始 `OPEN` 状态。缺少 C 地址、C 无法提供已审核快照、模型不可用、输出不合格或 C 写回失败时，A 分别返回冻结错误码：

- `KNOWLEDGE_QUALITY_INPUT_UNAVAILABLE`（503）
- `KNOWLEDGE_QUALITY_MODEL_UNAVAILABLE`（503）
- `KNOWLEDGE_QUALITY_OUTPUT_INVALID`（422）
- `KNOWLEDGE_QUALITY_WRITEBACK_FAILED`（502）

这些错误不包含资料正文、文件路径、请求体、密钥或模型原始输出。

## 验收与真实联调

单元测试只验证 A 的 HTTP、结构校验和安全边界，不代表真实跨服务成功。真实验收必须由 C 提供一条人工审核的去标识化快照，在隔离环境中人工触发一次运行，并保留 `material_id`、revision、content hash、`analysis_run_id`、模型版本、Prompt 版本与 C 中的 `ANALYZED` 结果。运营修复资料时必须在 C 创建新 revision；本 V1 不会把任何 revision 自动发布到 RAG。
