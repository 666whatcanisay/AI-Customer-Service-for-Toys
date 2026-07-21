# Admin web

Minimal Vue 3 administration shell for C-T01. It contains only `/system-status`, which reads the platform backend health endpoint and renders loading, healthy, offline, and server-error states. It contains no dashboard metrics or business modules.

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
