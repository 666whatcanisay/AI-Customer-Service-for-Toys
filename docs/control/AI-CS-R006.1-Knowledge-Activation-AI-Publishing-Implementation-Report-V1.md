# AI-CS R006.1 Knowledge Activation & AI Publishing Implementation Report V1

> 日期：2026-07-31
>
> 正式运行基线：`AI-CS@b7783f759776ecf7592ae198893ba5100d75be08`、数据库`0010_customer_available_catalog_v1`
>
> 实现分支：`feature/r006-1-knowledge-activation-v1`
>
> 实现代码HEAD：`407e8f0`
>
> 正式Runtime部署：未执行
>
> 最终状态：`R006_1_KNOWLEDGE_ACTIVATION_COMPLETE`

## 1. A上下文修复

A的`FrozenChatContext`已取消“只能是历史TEST租户/店铺/商品”的字面量限制，改为接收C/B明确提供的安全业务上下文。A仍然只在`tenant_id + platform + store_code + product_id + sku_id`范围检索和回答，不读取`customer_service_status`，不判断商品权限。

历史数据的`pdd`与C目录的`pinduoduo`只做传输别名兼容，不承载可信度判断。检索不再依赖`test_data_mode`、`production_usable`或`publishable`。当商品已经进入客服目录但active collection没有商品知识时，A返回“AI知识尚未同步，请人工核对”，不会编造回答。

实现提交：`4148ca3 feat(rag): publish approved product knowledge incrementally`。

## 2. 商品状态设计

C商品知识中心和商品详情现在并列展示三个独立状态：

| 业务维度 | 状态来源 | 状态 |
| --- | --- | --- |
| 资料状态 | R009/商品知识审核 | 待审核、已通过等既有状态 |
| 客服状态 | R006 Customer Available Catalog | `DISABLED / ENABLED` |
| AI知识状态 | R006.1发布投影 | `NOT_GENERATED / GENERATING / PUBLISHED / SYNC_FAILED / NEED_RESYNC` |

知识状态以规范文档SHA-256 fingerprint为版本标识。已发布fingerprint与当前fingerprint不同即显示`NEED_RESYNC`；客服状态变化不影响fingerprint，不触发向量化。

迁移`0011_product_knowledge_publishing_v1`只新增当前投影、发布收据和幂等记录三张表，已在隔离SQLite完成`0010 → 0011 → 0010 → 0011`往返验证。0010和R009的0009不修改。

## 3. AI知识发布流程

实现的受控流程为：

```text
APPROVED 商品知识
  ↓ C生成固定字段规范JSON与fingerprint（不调用LLM）
  ↓ A按商品增量切片
  ↓ Embedding
  ↓ 写入配置的active collection
  ↓ 回读校验chunks与embeddings
  ↓ 校验通过后删除该商品旧版本
  ↓ C保存PUBLISHED投影与publication receipt
```

相同fingerprint重复发布返回`changed=false`。失败时C记录`SYNC_FAILED`，A保留旧版本；不会全量删除或重建其他商品、其他集合。A内部发布接口仅允许loopback调用。

实现提交：

- `88887a7`：Contracts 0.4.0、schema、错误码、兼容说明和Interface Freeze；
- `4148ca3`：A上下文、增量发布、可见性和检索兼容；
- `be89e57`：C生命周期、0011、规范文档、收据和批量启用；
- `74960ee`：C Admin三状态、批量启用、发布与可见性展示；
- `9b42b2e`：运行配置将C发布请求指向同一Runtime的A端口。
- `407e8f0`：统一LOCAL C运行环境生成并覆盖C→A、Admin→C/A目标端口测试。

## 4. RAG同步结果

隔离验收使用正式数据库和Chroma的只读快照，不共享正式可写路径。浏览器对商品“(限量特价/袋装)机关山洞螺旋升降5机关/送2飞龙”执行首次发布：

| 证据 | 结果 |
| --- | --- |
| 发布状态 | `PUBLISHED` |
| Active collection | `test_knowledge_v031` |
| 新增商品chunks | 3 |
| Embeddings | 3 |
| 当前/已发布fingerprint | 完全一致：`539390be...3916` |
| Publication receipt | `RAG-e80185f3d9d853e704262561b40d61a0` |
| 正式Chroma | 未写入，仍为既有47 chunks |

隔离状态矩阵共24个商品：资料`APPROVED=19`、历史`TEST_CONFIRMED=5`；客服`ENABLED=6`、`DISABLED=18`；新生命周期`PUBLISHED=1`、`NOT_GENERATED=23`。新发布账本共3 chunks/3 embeddings。历史47个TEST chunks继续可检索，但因为没有R006.1发布收据，不被伪装成新生命周期的`PUBLISHED`。

## 5. UI修改

保持原Admin设计语言，只在现有商品知识中心和商品详情增加：

- 明确的“资料审核 → 客服可用 → AI可用”说明；
- 每商品三类独立状态和RAG chunks；
- “只看待客服启用”、商品勾选与批量启用按钮；
- 单商品“同步AI知识”“检查RAG状态”“查看发布收据”；
- 商品级collection、chunks、embeddings、fingerprints和更新时间。

Import Center、R009导入页面与B客服业务流程未修改。启用客服和发布AI知识仍是两个独立人工动作。

浏览器证据保存在Git忽略的隔离目录：

- `.runtime/r006-1/evidence/01-admin-before-publish.png`
- `.runtime/r006-1/evidence/02-admin-ai-published.png`
- `.runtime/r006-1/evidence/03-admin-customer-enabled.png`
- `.runtime/r006-1/evidence/04-admin-rag-visibility.png`
- `.runtime/r006-1/evidence/05-customer-ai-answer.png`
- `.runtime/r006-1/evidence/06-admin-rag-visibility-viewport.png`
- `.runtime/r006-1/evidence/07-admin-rag-panel-viewport.png`

## 6. 测试结果

### 6.1 自动测试

| 范围 | 结果 |
| --- | --- |
| A Backend | `108 passed, 3 skipped`；新增非TEST上下文、平台别名、增量发布、幂等、旧版本保护、可见性和未同步拒答覆盖 |
| C Platform Backend | `115 passed`；含APPROVED限制、发布/检查/收据、失败状态、批量逐条隔离、0011往返 |
| B Frontend | `28 files / 117 tests passed`，typecheck和build通过；B业务流程零修改 |
| C Admin | `26 files / 62 tests passed`，typecheck和build通过 |
| Contracts | `4 passed`；version=`0.4.0`，旧schema保留，新schema有效 |
| Windows OPS | Runtime Entry Alignment、Runtime Fix2等前六套通过；`Test-OpsT04Fix1.ps1`在其既有“过期PID”子进程场景被PowerShell`NativeCommandError`测试夹具中断，产品脚本语法、隔离启动和正式status均通过 |

### 6.2 完整浏览器验收

隔离端口：Admin 15184、C API 18013、A 18003、B 15183；隔离数据库revision为0011。完成的真实UI链路：

```text
Admin查看 APPROVED / 客服禁用 / AI未生成
  ↓ 点击同步AI知识
Admin显示 PUBLISHED / 3 chunks / 3 embeddings / 发布收据
  ↓ 勾选商品并批量启用
Admin显示客服已启用 / activation receipt结果
  ↓ B选择玩趣乐园积木店
B实时出现刚启用商品
  ↓ 提问“这款积木适合几岁？是什么材质？”
A回答“5岁以上、ABS塑料”，附3条同商品引用
```

回答继续显示`SUGGESTION_ONLY；AUTO_SEND_DISABLED`以及小零件安全提示。验收后隔离四服务已停止；正式5173/5174/8000/8011保持`b7783f7`、`standard/LAN`、数据库0010、active collection 47 chunks且全部RUNNING。

## 7. 剩余风险与发布入口

1. 本任务完成的是实现与隔离浏览器验收，不是正式发布。正式上线必须另建Release Candidate，备份正式数据库，执行0011，四服务同SHA部署并完成回滚检查。
2. 23个未进入新发布账本的商品仍明确显示`NOT_GENERATED`；不得批量自动发布。运营应逐商品或受控批次确认后发布。
3. 历史TEST向量没有R006.1 fingerprint/receipt元数据，继续按历史路径可用；若迁入新生命周期，应显式重新发布，不能伪造收据。
4. B现有“AI参考准备度”仍读取旧的知识资料审核接口，浏览器出现“暂无已审核资料”，但回答已正确使用R006.1的3条商品引用。该提示语不影响检索结果，登记为P2展示一致性问题；本任务禁止修改B业务流程，因此未越界修复。
5. Windows全套OPS回归中的`Test-OpsT04Fix1.ps1`存在测试夹具对预期错误流处理不兼容（`BUG-RUNTIME-003`）；受影响的正式启停脚本没有运行故障，但应在独立OPS测试治理任务中修复夹具。
6. 生产安全仍保持人工确认、禁止自动发送、禁止自动退款、禁止订单或ERP写入；本功能不能作为正式鉴权或RBAC的替代。

下一入口：`R006.1 Production Release V1`，而不是继续修改R009、B工作流、Prompt或全量RAG。
