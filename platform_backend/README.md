# Platform backend

C-line FastAPI service. It owns the production IAM V1 user, role, opaque session and Store-binding records, in addition to the existing product, knowledge and operations capabilities. It does not own RAG/model behavior, PDD integration or browser automation.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
$env:CORS_ALLOWED_ORIGINS = "http://127.0.0.1:5173"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

The normal Windows production wrapper runs `alembic upgrade head` before it starts this service. After an authorized backup, IAM requires at least `0013_user_management_v1`; Store Context Resolver V1 adds `0014_store_context_resolver_v1`, and Customer Desktop Workflow V1 adds the minimized `0015_customer_desktop_workflow_v1` audit table. Use a repository wrapper so the CLI reads the same controlled database configuration. Passwords are read by Python `getpass` and must never be supplied on the command line or stored in a script:

```powershell
..\scripts\windows\bootstrap_ai_cs_admin.ps1 -Username admin -DisplayName "系统管理员"
..\scripts\windows\bootstrap_ai_cs_initial_users.ps1
```

The initial-users wrapper contains only the approved non-secret identities. It normalizes usernames with NFKC plus casefold for duplicate detection, skips existing accounts without changing their credential, role, status or Store bindings, and prompts only when an account is missing. Direct CLI use is safe only when the process already has the exact production `DATABASE_URL`; otherwise it may target the local default database.

IAM endpoints are under `/api/v1/auth` and ADMIN-only user management is under `/api/v1/admin/users`. Browser-facing business endpoints require a Bearer session and are authorized on the server. New or reset accounts always have `must_change_password=true`; business permissions fail closed until `/api/v1/auth/change-password` succeeds. `CUSTOMER_SERVICE` users may start with no Store, then use `/api/v1/auth/store-options` and `/api/v1/auth/store-bindings` to select one or more enabled customer Stores plus one default; `/api/v1/auth/default-store` switches only within that authorized set. `OPERATOR` and `ADMIN` receive all-Store scope from their role. The Customer Workspace derives identity and effective Store from `/api/v1/workspace/context`, resolves Product/SKU through `/api/v1/workspace/context-resolutions`, and may pass a ready `resolution_id` to `/api/v1/workspace/ai-replies`. Resolution audit persistence contains a content hash and entity IDs only, never customer text. Session lifetime defaults to 480 minutes and can be changed with `IAM_SESSION_TTL_MINUTES`.

Customer Desktop Workflow V1 exposes authenticated C facades at `GET /api/v1/workspace/desktop-agent` and `POST /api/v1/workspace/desktop-agent/binding-grants`; `GET /api/v1/admin/desktop-workflow/audit` is ADMIN-only. C derives user and Store references from the authenticated session, returns only matching device status, and never sends the Channel Engine operator credential to the browser. Self-service grant creation is limited to a `CUSTOMER_SERVICE` user, an authorized Store and an already registered `UNBOUND` Agent/device; activation remains a separate Channel Engine administrator action.

The integration is disabled by default. Configure it through the production wrapper, using only an external UTF-8 single-line session reference file:

```powershell
$ChannelAgentIntegrationEnabled = $true
$ChannelAgentServerUrl = 'https://channel-agent.internal.example'
$ChannelAgentOperatorSessionReference = 'runtime\secrets\channel-agent-operator-session.txt'
$ChannelAgentTimeoutSeconds = 5
```

Non-loopback plain HTTP is rejected; remote use requires HTTPS. The referenced file must resolve inside the controlled Runtime directory and is read on demand, while its content is never copied into Git config, reports or browser responses. When integration is disabled, unreachable, unauthorized or contract-incompatible, C returns a non-2xx Error Envelope with a distinct error code.

`GET /health` returns service status and a request ID. Product/SKU import endpoints are under `/api/v1`; the fixed template is served by `GET /api/v1/import-templates/product-sku`.

`POST /api/v1/import-batches/product-sku/preflight` analyzes the same multipart `.xlsx` input entirely in memory. It reuses import file-safety, parser, normalizer, validator, duplicate, and conflict rules, but has no database dependency and creates no batch or staged row. The existing formal upload endpoint remains unchanged.

C-T02B adds an isolated V0.3.1 test-package path under `/api/v1/test-data-packages` plus frozen read-only `/test-catalog` and `/test-knowledge-packages` endpoints. ZIP preflight first validates every physical entry for safe paths, duplicate paths, links, encryption, and size limits, then accepts either a root `manifest.json` or one safe wrapping directory whose immediate logical root contains `manifest.json`. Manifest paths, file-set checks, hashes, workbooks, and evidence paths always use that in-memory logical root; the upload bytes and their SHA-256 are never rewritten. Imported data is fixed to `TENANT-PDD-SM-TEST`; attachment bytes and raw RTF are never stored or returned.

C-T05 adds local customer-suggestion persistence plus read-only `/api/v1/admin/*` projections. Suggestions always start as `SUBMITTED`; only lifecycle status and `internal_note` are administrative writes. No catalog data, source file, product, FAQ, safety rule, or conflict is editable through these endpoints. Source projections omit absolute paths and raw source payloads.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Configuration is loaded from environment variables documented in `.env.example`. The application does not automatically read `.env` files.

`CORS_ALLOWED_ORIGINS` is a comma-separated list of complete browser origins. Its safe local default is only `http://127.0.0.1:5173`. If the browser is opened with `localhost`, add `http://localhost:5173` explicitly. Wildcards, empty lists, non-HTTP(S) URLs, credentials, paths, queries, and fragments are rejected during application startup. CORS is only a browser boundary; Bearer authentication and server-side RBAC remain mandatory.

The local default is `sqlite:///./platform.db`. Database files, uploaded source files, logs, environments, and dependencies are Git-ignored. The parser processes the upload in memory and does not retain the workbook itself.
