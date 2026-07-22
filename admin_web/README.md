# Admin web

Vue 3 administration shell for the C-line platform. It keeps the C-T01 `/system-status` page and adds the C-T02 review-only import workflow:

- `/imports`: real API-backed batch list and explicit empty/error/loading states;
- `/imports/new`: fixed-template download, `.xlsx`/5 MB client checks, zero-write preflight summary, `can_import` upload gate, upload progress, and server result summary;
- `/imports/:batchId`: batch counts, status filtering, row issues, and error-report download.

The UI cannot approve, publish, edit formal products, call RAG, or display fabricated dashboard statistics.

## Local setup and checks

```powershell
pnpm install
pnpm typecheck
pnpm test
pnpm build
```

## Run

Start `platform_backend` on `127.0.0.1:8000`, then run:

```powershell
pnpm dev
```

Vite proxies `/api/platform/*` to the platform backend in local development. Copy `.env.example` to an untracked `.env` only when an alternate API base URL is needed.
