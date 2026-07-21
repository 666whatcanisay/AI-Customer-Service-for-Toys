---
name: rag-baseline-guardian
description: Use before auditing, migrating, refactoring, or regression-protecting a legacy RAG project or its baseline assets.
---

# RAG baseline guardian

1. Record the Git revision and cleanliness, API behavior, test evidence, and rollback baseline before changing anything.
2. Compare before and after results for API behavior, retrieval Top-K, citations, answer actions, refusals, and latency.
3. Treat Mock evidence separately from real-model evidence.
4. Return `BLOCKED` when a material risk cannot be verified.
5. After an accepted task, update `docs/rag` status, change, handoff, and `machine-context.json`; do not start the next task automatically.

Never clear or overwrite `vector_db`, modify the real `knowledge_base`, or automatically run a full rebuild.
