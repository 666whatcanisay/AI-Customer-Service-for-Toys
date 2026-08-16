# AI-CS Portable GitHub Monorepo V1 Task Card

- Requirement: `R-GITHUB-PORTABLE-MONOREPO-V1`
- Date: `2026-08-16`
- Owner: `CONTROL / OPS / QA`
- Status: `DONE`
- Target: `PORTABLE_MONOREPO_RELEASE_READY`

## Goal

Publish AI-CS and AI-CS Channel Execution Engine as one reproducible GitHub repository. A fresh Windows clone must support dependency bootstrap, isolated runtime creation, development startup and continued work without depending on the original computer's absolute paths.

## Scope

- Import the complete AI-CE source history under `AI-CS-Channel-Execution-Engine/`.
- Preserve AI-CS at the repository root and keep shared contracts unchanged.
- Remove hard-coded local repository paths while retaining compatibility with the former sibling-repository layout.
- Add portable bootstrap, doctor, start and stop entries.
- Replace the historical front page with current architecture, setup, operating boundary and handoff documentation.
- Add repository CI, perform a forbidden-asset/secret scan and verify a clean clone.

## Safety boundary

- Never commit `.env`, runtime secrets, SQLite databases, vectors, source knowledge, logs, browser profiles, customer content, cookies, tokens, dependencies or build output.
- GitHub contains source and sanitized demonstrations only. Production data and credentials must be recreated locally.
- Existing remote release branches remain available; this release uses a new branch and tag.

## Acceptance

1. AI-CS and AI-CE source are present in one Git history.
2. The checkout directory may have any name.
3. PowerShell/Python path tests, selected backend tests, both frontend typechecks/builds and CE tests pass.
4. A clean clone in a path containing spaces passes repository doctor and source checks.
5. Final Git status is clean and GitHub release metadata references the final commit.

## Verification result

- AI Core: `268 passed, 3 skipped`
- Platform: `221 passed`
- Customer UI: `236 passed`; typecheck and build passed
- Admin UI: `117 passed`; typecheck and build passed
- AI-CE: `948 passed, 2 skipped`
- Portable PowerShell layout checks: passed
- Bootstrap/Doctor on the source workspace: passed
