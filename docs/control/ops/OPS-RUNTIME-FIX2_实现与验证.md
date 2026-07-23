# OPS-RUNTIME-FIX2 implementation and verification

Date: 2026-07-23
Gate: L2 local runtime orchestration
Scope: scripts/windows/** and docs/control/ops/** only

## Delivered

- Added backward-compatible optional runtime values for the Ollama API address, C SQLite URL, test package ID, and automatic A knowledge sync.
- Runs C Alembic migration before C starts; migration failure blocks C.
- Imports the configured test ZIP only if the configured package ID is absent. A safe one-directory ZIP normalization is written only under ignored runtime state.
- Starts A with explicit Ollama and C API environment variables, waits for the strict A status gate, requires a 47/47 sync, and runs a sourced non-fallback Ollama chat smoke before B starts.
- Expanded status output with migration revision, test-package presence, latest sync count, A model status, Ollama address/model, and page address.
- Retains unknown-process protection. When Windows does not disclose a command line, safe stopping falls back only to the recorded executable path and exact start time.

## Verified evidence

- A new temporary SQLite database migrated from empty state through both revisions.
- Re-running against the migrated database completed without a new migration revision.
- First import accepted the approved V0.3.1 test package; the repeat run skipped the matching PDD-SM-2026-001-TEST package.
- Automatic A sync returned synced_items=47 and collection_count=47 on both runs.
- A passed ready=true, model_configured=true, initialization_error=null and a real local Ollama chat smoke.
- B returned HTTP 200. The status script reported the requested runtime state.
- Managed B, A, and C processes were identity-validated, stopped, and had their records removed.
- Unit checks covered configuration compatibility, unavailable Ollama, absent model, model_configured=false, unknown port protection, ZIP normalization, and PowerShell parsing.

## Boundaries

No dependencies or models were installed, no firewall setting changed, no unknown process was terminated, and no ZIP, database, vector store, log, local configuration, or customer data was committed. This is a test-data local-runtime verification, not a production or security certification.
