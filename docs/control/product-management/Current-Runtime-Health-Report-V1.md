# AI-CS Current Runtime Health Report V1

检查日期：2026-07-30

结论：`RUNTIME_HEALTH_PASS / BUSINESS_CATALOG_BLOCKED`

## 1. 运行身份

- Repository root：`C:\Users\EDY\Documents\Codex\2026-07-21\AI-CS`
- Branch：`stabilization/product-stable-runtime-v1`
- Git SHA：`42bafcf6630ccbcd1c2dd1d55cb7d3fe735cb1e2`
- Git：clean
- runtimeMode：四服务均为 `standard`
- networkMode：四服务均为 `LAN`
- 配置：`.runtime/phase-e/config/green-standard.local.ps1`
- 正确状态入口：`scripts/windows/status_lan_ai_customer_service.ps1`

## 2. 四服务

| 服务 | 端口/入口 | 最终受管 PID | 最终监听 PID | Health | 身份 |
| --- | --- | ---: | ---: | --- | --- |
| B 客服 | `192.168.1.11:5173` | 31776 | 31776 | HTTP 200 | `42bafcf` / standard / LAN |
| C Admin | `127.0.0.1:5174` | 36104 | 19276 | HTTP 200 | `42bafcf` / standard / LAN |
| A AI | `127.0.0.1:8000` | 35952 | 36656 | health/status 200 | `42bafcf` / standard / LAN |
| C API | `127.0.0.1:8011` | 8648 | 28652 | health 200 | `42bafcf` / standard / LAN |

运行测试完成三轮 `stop → start → status`。每轮四服务均回到同一 SHA、相同模式和健康状态；最终 PID 为第三轮及故障恢复后的记录。

## 3. 数据与依赖

- 正式数据库：`.runtime/phase-e/data/standard-platform.sqlite3`
- Revision：`0008_customer_feedback_loop_v1`
- SQLite integrity：`ok`
- 正式测试前备份：`.runtime/phase-e/green-standard/pilot-backups/platform-20260730-235357.sqlite3`
- R009 仅在隔离 0009 数据库验收，正式库未出现 R009 表和导入批次。
- Chroma active collection：`test_knowledge_v031`
- Active chunks：47
- Available collections：`documents=0`、`test_knowledge_v031=47`
- Ollama：`http://127.0.0.1:11434`
- 模型：`qwen3.5:9b`，真实 `/api/chat` 推理通过。

## 4. 故障恢复

- A 停止时，B 显示“AI 待连接 / AI 服务不可用，请稍后重试或按原客服流程处理”；C 仍可用。恢复后四服务健康。
- C API 停止时，B 显示“平台 待连接 / 数据服务不可用”；A 仍可用。恢复后四服务健康。
- 未修改数据库结构、正式业务数据、Chroma、模型或 Prompt。

## 5. 健康与业务 Gate 的区别

基础运行健康已通过，但 B 商品选择主流程仍被 `BUG-B-001` 阻断：C 返回的一条不兼容店铺会触发 B 清空全部目录。该问题的正确入口是已冻结但尚未授权实施的 R006 C 最终投影，不能在本冲刺中用 B 临时过滤或修改数据规避。
