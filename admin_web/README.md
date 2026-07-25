# Admin web

Vue 3 administration shell for the C-line platform. It keeps the C-T01 `/system-status` page and adds the C-T02 review-only import workflow:

- `/imports`: real API-backed batch list and explicit empty/error/loading states;
- `/imports/new`: fixed-template download, `.xlsx`/5 MB client checks, zero-write preflight summary, `can_import` upload gate, upload progress, and server result summary;
- `/imports/:batchId`: batch counts, status filtering, row issues, and error-report download.
- `/test-data-packages`: V0.3.1 ZIP preflight/import, exact test counts, import status, and explicit test-only/production-disabled/auto-send-disabled restrictions.
- C-T05 adds a read-only operations portal: real overview counts, stores, products/SKUs, FAQs, safety rules, sources, conflicts, import records, and persisted customer-suggestion lifecycle handling.
- `/ai-capabilities` probes only the task-declared A-line module endpoint. It has no mock fallback; if A is unavailable or unmerged it shows that fact and keeps online test controls disabled pending a versioned A contract.

The UI cannot approve, publish, edit formal products, call RAG, or display fabricated dashboard statistics.

## Local setup and checks

```powershell
pnpm install
pnpm typecheck
pnpm test
pnpm build
```

## Run

Start `platform_backend` on `127.0.0.1:8011` and the A service (when available) on `127.0.0.1:8000`, then run:

```powershell
pnpm dev
```

Vite proxies `/platform-api/*` to the C platform backend and `/ai-api/*` to the A service in local development. Copy `.env.example` to an untracked `.env` only when an alternate API base URL is needed.
