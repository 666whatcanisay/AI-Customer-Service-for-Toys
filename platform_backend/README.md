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
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`GET /health` returns service status and a request ID. Product/SKU import endpoints are under `/api/v1`; the fixed template is served by `GET /api/v1/import-templates/product-sku`.

`POST /api/v1/import-batches/product-sku/preflight` analyzes the same multipart `.xlsx` input entirely in memory. It reuses import file-safety, parser, normalizer, validator, duplicate, and conflict rules, but has no database dependency and creates no batch or staged row. The existing formal upload endpoint remains unchanged.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Configuration is loaded from environment variables documented in `.env.example`. The application does not automatically read `.env` files.

The local default is `sqlite:///./platform.db`. Database files, uploaded source files, logs, environments, and dependencies are Git-ignored. The parser processes the upload in memory and does not retain the workbook itself.
