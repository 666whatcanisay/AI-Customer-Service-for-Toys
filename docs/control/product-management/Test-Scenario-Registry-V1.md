# AI-CS Test Scenario Registry V1

## AI-CS V1.0.0 Production Finalization

| ID | 场景 | 结果 | 证据 |
| --- | --- | --- | --- |
| PF-001 | 全量自动化回归 | PASS | A 109 passed/3 skipped；B 120；C全量通过并追加contracts 5；Admin 64；B/Admin typecheck与build通过 |
| PF-002 | 数据库0012与数据保护 | PASS | `integrity_check=ok`；INITIAL_IMPORT ENABLED=1、PILOT ENABLED=1；Product、receipt、publication与迁移历史保留 |
| PF-003 | RAG与模型连续性 | PASS | 内部集合`test_knowledge_v031=56 chunks`；`qwen3.5:9b` ready；未全量重建、未删除chunks/embeddings |
| PF-004 | 四服务正式版本 | PASS | standard/LAN；B 5173、Admin 5174、A 8000、C 8011健康且同一tag SHA |
| PF-005 | Admin正式体验 | PASS | 正式页面文案、商品知识状态与六类模板入口可见；开发测试入口默认隐藏 |
| PF-006 | B客服与安全边界 | PASS | 已发布商品显示3 chunks/3 citations；人工确认、不自动发送、不自动退款、不修改订单提示有效 |
| PF-007 | 备份与回滚证据 | PASS | 在线/离线SQLite与0011重建快照完整；RAG离线manifest为`bbdcbcded050991cbfda91d90dd3887acc93f77a5ae840a65469549230da1` |

以上是V1.0.0正式化回归，不替代R003完整业务验收、R005真实Feedback Loop验证或R007第二终端网络验收。

## Runtime

| ID | 场景 | 结果 | 证据 |
| --- | --- | --- | --- |
| RT-001 | stop/start/status 连续三轮 | PASS | 每轮四端口同 SHA、standard/LAN、health 200 |
| RT-002 | A 服务异常 | PASS | B 显示 AI 待连接和安全降级提示；恢复后健康 |
| RT-003 | C API 异常 | PASS | B 显示平台待连接和数据服务不可用；恢复后健康 |
| RT-004 | 数据保护 | PASS | 0008/0010历史备份保留；0012在线、离线及重建0011快照完整，Product、receipt、publication和RAG数据未删除 |

## B 客服

| ID | 场景 | 结果 | 说明 |
| --- | --- | --- | --- |
| B-001 | 正常商品咨询 | READY FOR BUSINESS REGRESSION | 正式浏览器已可选择1个店铺和5个商品；完整提问/回答验收未在发布Smoke中执行 |
| B-002 | 不存在商品 | PARTIAL PASS | B 错误页可理解；A 级不存在商品 `REFUSE/sources=0` |
| B-003 | 资料不足 | PARTIAL PASS | A 级拒答通过；B目录阻塞已解除，浏览器端完整回归待执行 |
| B-004 | 多 SKU | PARTIAL PASS | A 级三 SKU 来源隔离通过；B目录阻塞已解除，浏览器端完整回归待执行 |
| B-005 | 商品切换 | PARTIAL PASS | A 级商品来源隔离通过；B目录阻塞已解除，浏览器端完整回归待执行 |
| B-006 | 连续 5 轮 | PARTIAL PASS | A API 五轮稳定；B目录阻塞已解除，浏览器端完整回归待执行 |

## C 运营

| ID | 场景 | 结果 | 说明 |
| --- | --- | --- | --- |
| C-001 | 商品查看/新增/编辑/状态 | PASS | 隔离环境完成合成商品操作，不发布 |
| C-002 | 商品知识中心 | PASS | 页面、字段和状态可见；R009 审核结果入隔离正式表 |
| C-003 | Import Center | PASS | 六类模板下载入口均存在，定位未变 |
| C-004 | R009 导入 | PASS | 浏览器真实上传、解析、Merge、审核、幂等 |
| C-005 | AI 问题中心 | PASS | 页面正常并显示真实空状态 |

## R009

| ID | 场景 | 结果 | 证据 |
| --- | --- | --- | --- |
| R009-001 | 正常上传 | PASS | 真实模板、4 Sheet、19 商品、浏览器审核 |
| R009-002 | 空模板 | PASS | `PREFLIGHT_FAILED`，无正式写入 |
| R009-003 | 缺商品名称 | PASS | `REQUIRED_FIELD_MISSING`，产品表 0 写入 |
| R009-004 | 错误店铺 | PASS | 整批 `PREFLIGHT_FAILED` |
| R009-005 | 重复上传 | PASS | 幂等 replay/`NO_CHANGE`，无重复产品 |
| R009-006 | 100 条解析 | PASS | 纯代码解析 100 行，稳定性预算小于 1 秒 |

## AI 质量

| ID | 场景 | 结果 |
| --- | --- | --- |
| AI-001 | 知识存在 | PASS：年龄和玩法受控回答，有正确来源 |
| AI-002 | 知识不存在 | PASS：`REFUSE`、sources=0 |
| AI-003 | 退款/安全/责任高风险 | PASS：人工转接，`SUGGESTION_ONLY`、`AUTO_SEND_DISABLED` |
