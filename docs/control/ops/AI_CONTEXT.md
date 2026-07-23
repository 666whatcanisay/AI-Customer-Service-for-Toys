# OPS-T04 AI Context

- Scope: local Windows test runtime only; no business code or shared contracts.
- Root: a merged repository containing `backend`, `frontend`, and `platform_backend`.
- Entry commands: C and A use their configured virtual-environment Python with Uvicorn; B uses local Vite through Node.
- Default endpoints: C `127.0.0.1:8011/health`, A `127.0.0.1:8000/api/health`, B `127.0.0.1:5173/`.
- Dependency policy: validate only; never install packages, download models, alter firewall rules, or write secrets.
- Model prerequisite: local Ollama with `qwen3.5:9b`.
- Runtime state: `<RepositoryRoot>/.runtime`, Git-ignored; records PID, executable path, working directory, start time, command feature, port, and logs.
- Port safety: an occupied port is never killed. The operator must resolve unknown owners manually.
- Stop safety: only recorded processes are stopped after PID, executable path, start time, and command-feature validation.
- Optional data import: only a configured local ZIP is posted to C after C health succeeds; disabled by default.
- Current integration caveat: cross-line live compatibility remains an integration concern; successful script launch does not certify business workflow readiness.
