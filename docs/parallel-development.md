# Parallel development

| Line | Allowed paths |
| --- | --- |
| A: RAG Core | `backend/**`, `docs/rag/**` |
| B: User client | `frontend/**`, `extension/**`, `docs/customer/**` |
| C: Platform center | `platform_backend/**`, `admin_web/**`, `docs/platform/**` |

`contracts/**` is shared. Any breaking contract change must update its JSON schema, `contracts/version.json`, `contracts/CHANGELOG.md`, and compatibility notes in the PR. Coordinate before making it.
