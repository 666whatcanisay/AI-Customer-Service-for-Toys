# 架构说明

```text
C version V0.3.1 / schema 0.3.1-test -> validation -> test_knowledge_v031
                                            |
question + frozen context -> scoped Chroma query
                          -> safety action arbitration
                          -> Ollama (DIRECT/CONTROLLED only)
                          -> frozen data response
```

`documents` 与 `test_knowledge_v031` 是独立 Chroma Collection。同步只 upsert 测试包稳定 ID，不清空原索引。所有 A-T03 测试使用临时向量目录。

过滤的硬边界为 tenant/platform/store/product；SKU 存在时精确 SKU 优先并允许同商品的商品级回退，SKU 为空时只允许商品级知识。店铺级分支只接受 SAFETY_RULE 或满足 HIGH + guarded action 的空商品 FAQ；评测内部 sentinel 不会放宽公开 chat。安全动作 ASK_CLARIFY、REQUIRE_LOOKUP、TRANSFER_HUMAN、REFUSE 直接返回受控文本，不经过模型；接近最近结果的安全知识按小距离窗提升。
