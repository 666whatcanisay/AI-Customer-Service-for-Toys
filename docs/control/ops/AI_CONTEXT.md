# OPS-T04 AI Context

- Scope: local Windows test runtime only; no business code or shared contracts.
- Root: a merged repository containing `backend`, `frontend`, and `platform_backend`.
- Entry commands: C and A use their configured virtual-environment Python with Uvicorn; B uses local Vite through Node.
- Default endpoints: C `127.0.0.1:8011/health`, A `127.0.0.1:8000/api/health`, B `127.0.0.1:5173/`.
- Dependency policy: validate only; never install packages, download models, alter firewall rules, or write secrets.
- Model prerequisite: an Ollama API at the configurable `OllamaBaseUrl` (default `http://127.0.0.1:11434`) with `qwen3.5:9b`.
- Runtime state: `<RepositoryRoot>/.runtime`, Git-ignored; records PID, executable path, working directory, start time, command feature, port, and logs.
- Port safety: an occupied port is never killed. The operator must resolve unknown owners manually.
- Stop safety: only recorded processes are stopped after PID, executable path, start time, and command-feature validation.
- Platform runtime: the configured `PlatformDatabaseUrl` is migrated with `alembic upgrade head` before C can start; a migration failure blocks C.
- Test package: the configured ZIP is preflighted and imported only when the configured `TestKnowledgePackageId` does not already exist. A single-root ZIP is accepted directly; a safely identified one-directory ZIP is copied only to ignored runtime state with its top directory removed.
- A runtime gate: A receives explicit Ollama and C API environment values, then must report `ready=true`, `model_configured=true`, and `initialization_error=null`. When `AutoSyncTestKnowledge=true`, startup requires a 47/47 test-knowledge sync and a non-fallback Ollama chat smoke before B starts.
- Verified 2026-07-23: empty and already-migrated temporary SQLite databases, first import and idempotent import skip, real local Ollama chat, B HTTP 200, status reporting, managed stop, unknown-process protection, and PowerShell syntax passed. This remains a test-data-only local runtime, not a production certification.
