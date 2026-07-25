# 客服经验案例评测消费者（MVP-PLUS-01）

## 目的与边界

A 只在人工显式请求时评测一条由 C 审核通过的客服经验案例。它不训练模型、不修改 Prompt、不发布知识、不发送客户消息，也不写 ERP。C 仍然是案例、审核状态、不可变快照和评测证据的唯一数据源。

## 调用链

```text
POST A /api/admin/ai/experience-evaluations/run {case_id, revision}
  -> GET C /api/v1/admin/ai-optimization/cases/export
  -> local Ollama /api/chat (configured qwen3.5:9b)
  -> POST C /api/v1/admin/ai-optimization/evaluation-results
```

导出端点只提供 `APPROVED` 且尚未评测的不可变快照。A 逐页读取此端点，仅匹配请求的 `case_id` 与 `revision`，并保留快照原样的 `export_revision`、`content_hash` 回写。A 不访问 C 数据库或内部模块。

## A 端点

```http
POST /api/admin/ai/experience-evaluations/run
Content-Type: application/json

{"case_id":"CEC-example","revision":1}
```

成功响应沿用 A 的 envelope；`data` 是 C 已记录的评测证据。A 不在响应中返回导出快照、模型提示词、环境变量或密钥。

Ollama 必须返回可解析 JSON：

```json
{
  "result": {
    "outcome": "KEEP",
    "summary": "简短且不执行任何动作的评测摘要",
    "dimensions": {
      "faithfulness": "PASS",
      "safety": "PASS",
      "coaching_value": "PASS"
    }
  },
  "suggestions": [
    {
      "category": "COACHING",
      "description": "只提出人工后续可考虑的建议"
    }
  ]
}
```

`outcome` 仅为 `KEEP`、`NEEDS_REVIEW` 或 `REJECT`；建议类别仅为 `PROMPT_HYPOTHESIS`、`KNOWLEDGE_GAP`、`POLICY_GAP`、`COACHING`。建议不是自动执行指令。

## 冻结错误码

| HTTP | code | 含义 |
| --- | --- | --- |
| 503 | `EXPERIENCE_EVALUATION_EXPORT_UNAVAILABLE` | C 导出不可用、无此 APPROVED 快照或导出格式不可信。 |
| 503 | `EXPERIENCE_EVALUATION_MODEL_UNAVAILABLE` | 未配置 Ollama、模型不可用或调用失败。 |
| 422 | `EXPERIENCE_EVALUATION_OUTPUT_INVALID` | 模型输出不是受限的有效评测 JSON；不会回写。 |
| 502 | `EXPERIENCE_EVALUATION_WRITEBACK_FAILED` | C 未接受评测回写；不会重试或篡改快照。 |

## 配置与隐私

- `PLATFORM_API_BASE_URL`：C 的根地址，复用已有运行时配置。
- `PLATFORM_API_TIMEOUT_SECONDS`：C 请求超时，复用已有运行时配置。
- `EXPERIENCE_EVALUATION_PROMPT_VERSION`：可选；默认 `experience-evaluation-v1`，仅作为可追溯标签。
- `LLM_PROVIDER=ollama`、`LLM_MODEL=qwen3.5:9b`、`LLM_BASE_URL`：沿用本机真实模型配置。

请求仅在内存中用于本次模型调用；A 不在日志、运行指标或 API 响应中保留客户问题、原始回答、完整提示词或机密。单元测试可替换 HTTP 边界；任何“真实通过”声明必须来自实际 Ollama 与实际 C export/writeback 联调。
