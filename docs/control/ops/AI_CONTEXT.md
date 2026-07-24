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

## MVP-BATCH-05 LAN entry (2026-07-24, merged and host-verified)

- Network boundary: customer browsers use one URL, `http://<selected-server-ip>:5173/`. Vite proxies only `/rag-api/**` to loopback A `127.0.0.1:8000` and `/platform-api/**` to loopback C `127.0.0.1:8011`; it is not an arbitrary forward proxy.
- Listener boundary: LAN mode binds A and C to `127.0.0.1` and B to the selected physical adapter IPv4. TCP 8000 and 8011 must not be opened in the firewall.
- LAN selection: `LanAddress='auto'` is re-evaluated on every start. Eligible adapters are Up, physical, private IPv4, and have a default gateway. Ethernet is preferred over WLAN; virtual, WSL, Hyper-V, Bluetooth, VPN/TUN, 169.254/16, and 198.18/15 are excluded. Equal-priority ambiguity requires `PreferredInterfaceAlias`.
- Runtime records now include parent PID and health URL. A record remains safe only when PID, parent relationship, executable path, start time, and command feature agree; listener descendants are accepted only when they belong to the verified record process.
- Operator tools: `检查AI客服防火墙.bat`, `配置AI客服防火墙.bat`, `删除AI客服防火墙规则.bat`, and `诊断AI客服局域网.bat`. Firewall configuration requires Administrator plus `CONFIGURE`, creates one fixed Private TCP 5173 rule limited to the selected subnet, and never changes VPN settings or the global firewall state. Diagnostics are read-only and write ignored reports under `.runtime/diagnostics/`.
- Merge record: PR #20 was squash merged as `dc48646`; one-default-gateway startup handling and diagnostic report construction were subsequently repaired and squash merged as `f21eed9` and `ca587d9` after real-host smoke exposed the two PowerShell-only execution paths.
- Host verification: Private Ethernet `192.168.1.11/24` with gateway `192.168.1.1` was selected while `iKuuuVPN` was detected but excluded. A/C/B listen on `127.0.0.1:8000`, `127.0.0.1:8011`, and `192.168.1.11:5173`. Through 5173, page and two fixed proxy health endpoints returned HTTP 200; catalog returned 1 store and 5 products; a sourced `qwen3.5:9b` chat returned `CONTROLLED_ANSWER`. Managed stop → port release → restart, status, and read-only diagnostics passed; Ollama remained available.
- Next handoff: use `http://192.168.1.11:5173/` from a company wired client. If a Wi-Fi client cannot route to this wired subnet after the controlled Private 5173 rule is checked, record `NETWORK_SEGMENTED` rather than an application defect.
