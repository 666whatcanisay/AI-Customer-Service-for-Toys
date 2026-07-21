# Contributing

## Ownership

A owns `backend/**` and `docs/rag/**`; B owns `frontend/**`, `extension/**`, and `docs/customer/**`; C owns `platform_backend/**`, `admin_web/**`, and `docs/platform/**`. `contracts/**` is shared. Do not modify another line's owned paths as part of an unrelated task.

## Branches, commits, and PRs

Create task branches from `develop` under the appropriate `agent/*` line. Never commit directly to `main`; do not force-push `main` or `develop`. Use focused Conventional Commit-style messages (for example, `feat(contracts): add feedback field`). PRs target `develop`, explain testing, scope, risks, and contract impact; use squash merge unless the maintainer directs otherwise.

## Tests and contract changes

Run the relevant backend tests or frontend build when those components exist. Contract changes must validate schemas and examples, update `contracts/version.json` and `contracts/CHANGELOG.md`, and document backward compatibility. Breaking changes require agreement from all affected lines.

## Data safety

Never commit credentials, customer PII, real chat logs, raw internal knowledge, vector databases, models, logs, local environments, or generated caches. Use fabricated or de-identified samples only.
