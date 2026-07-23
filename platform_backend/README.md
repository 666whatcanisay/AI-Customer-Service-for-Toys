# Platform backend

C-line FastAPI service. C-T02 adds an isolated, review-only product/SKU XLSX ingestion path on top of the C-T01 health baseline. Valid rows stop at `PENDING_REVIEW`; there is no publish, RAG, Kingdee, model-completion, authentication, or formal product CRUD capability.

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

`GET /health` returns service status and a request ID. Product/SKU import endpoints are under `/api/v1`; the fixed template is served by `GET /api/v1/import-templates/product-sku`.

`POST /api/v1/import-batches/product-sku/preflight` analyzes the same multipart `.xlsx` input entirely in memory. It reuses import file-safety, parser, normalizer, validator, duplicate, and conflict rules, but has no database dependency and creates no batch or staged row. The existing formal upload endpoint remains unchanged.

C-T02B adds an isolated V0.3.1 test-package path under `/api/v1/test-data-packages` plus frozen read-only `/test-catalog` and `/test-knowledge-packages` endpoints. ZIP preflight validates safe paths, manifest file set, sizes, SHA-256, test-only flags, sheets 00-08, counts, source references, and SKU relationships before any database write. Imported data is fixed to `TENANT-PDD-SM-TEST`; attachment bytes and raw RTF are never stored or returned.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Configuration is loaded from environment variables documented in `.env.example`. The application does not automatically read `.env` files.

`CORS_ALLOWED_ORIGINS` is a comma-separated list of complete browser origins. Its safe local default is only `http://127.0.0.1:5173`. If the browser is opened with `localhost`, add `http://localhost:5173` explicitly. Wildcards, empty lists, non-HTTP(S) URLs, credentials, paths, queries, and fragments are rejected during application startup. CORS does not provide authentication or authorization.

The local default is `sqlite:///./platform.db`. Database files, uploaded source files, logs, environments, and dependencies are Git-ignored. The parser processes the upload in memory and does not retain the workbook itself.
