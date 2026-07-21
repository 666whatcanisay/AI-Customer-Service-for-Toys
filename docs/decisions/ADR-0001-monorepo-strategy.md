# ADR-0001: Use one repository with three development lines

## Decision

Use one repository, `main` and `develop` integration branches, and three owned agent branches/worktrees.

## Rationale

The lines share request/response contracts, delivery standards, and coordinated product behavior. A monorepo makes contract review and compatible changes visible in one pull-request flow while ownership boundaries reduce incidental coupling.

## Consequences

Each line must respect path ownership and version shared contracts deliberately. Independent repositories were rejected because they would make synchronized contract release and compatibility validation harder at this stage.
