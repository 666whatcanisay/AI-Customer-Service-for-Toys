# Repository layout

The monorepo shares governance and contracts while keeping business ownership explicit. Application dependencies flow inward toward `contracts/`: `frontend`, `extension`, `backend`, `platform_backend`, and `admin_web` may consume contracts; contracts must not depend on any application. Documentation is scoped to its owning line. Integration tests may exercise public contract surfaces but must use synthetic data.

No application subtree may directly import another line's private implementation. Cross-line behavior is expressed through versioned schemas in `contracts/`.
