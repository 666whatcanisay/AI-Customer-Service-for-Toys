# AI Customer Service for Toys

This is an early-stage monorepo for an AI-assisted toy customer-service product. It is not represented as a production-ready customer-service system.

## Current baseline

No runnable legacy application was present in this workspace at repository setup time. The repository therefore contains only a safe collaboration foundation and shared contracts; it does not claim existing frontend, backend, PDF retrieval, vector search, local-model, or operational-script capabilities.

The planned development lines are: A — RAG Core and safe-answer services; B — customer client and browser extension; C — knowledge-governance platform and administration.

## Layout and ownership

- `backend/`, `docs/rag/`: A line
- `frontend/`, `extension/`, `docs/customer/`: B line
- `platform_backend/`, `admin_web/`, `docs/platform/`: C line
- `contracts/`: shared; compatibility-controlled
- `tests/contract/`, `tests/e2e/`, `scripts/`, `.github/`: integration-owned

See [repository layout](docs/architecture/repository-layout.md), [parallel development](docs/parallel-development.md), and [contributing](CONTRIBUTING.md).

## Local use

There is no application to start in this sanitized baseline. When applications are imported, use their documented commands without committing `.env`, knowledge source files, vector databases, model weights, logs, customer data, or real conversations. Contract checks can be run with `python -m pytest tests/contract` once test dependencies are introduced.

## Branches and worktrees

Work on `agent/rag-core`, `agent/user-client`, or `agent/platform-center`, created from `develop`; merge to `develop` by squash PR, then promote to `main`. Run `scripts/setup_worktrees.ps1` from the repository root to create the three adjacent worktrees. See [CONTRIBUTING.md](CONTRIBUTING.md) for full rules.
