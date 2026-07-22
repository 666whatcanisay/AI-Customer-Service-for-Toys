# 架构说明

```text
C V0.3.1 rag-export -> validation -> test_knowledge_v031
                                            |
question + frozen context -> scoped Chroma query
                          -> safety action arbitration
                          -> Ollama (DIRECT/CONTROLLED only)
                          -> frozen data response
```

`documents` 与 `test_knowledge_v031` 是独立 Chroma Collection。同步只 upsert 测试包稳定 ID，不清空原索引。所有 A-T03 测试使用临时向量目录。

过滤的硬边界为 tenant/platform/store/product；SKU 存在时精确 SKU 优先并允许同商品的商品级回退，SKU 为空时只允许商品级知识。安全动作 ASK_CLARIFY、REQUIRE_LOOKUP、TRANSFER_HUMAN、REFUSE 直接返回受控文本，不经过模型；接近最近结果的 SAFETY_RULE 可提升 CONTROLLED/TRANSFER/REFUSE。
