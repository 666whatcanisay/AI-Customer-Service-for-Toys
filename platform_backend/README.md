# Platform backend

Minimal FastAPI service for the C-line platform baseline. This task exposes only a health endpoint and does not include a database, authentication, knowledge workflows, RAG integration, or other business modules.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`GET http://127.0.0.1:8000/health` returns service status and a request ID. Supplying `X-Request-ID` reuses that identifier in the response header and body.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Configuration is loaded from environment variables documented in `.env.example`. The application does not automatically read `.env` files.
