# AI-CS Production Architecture Convergence V2

## Frozen runtime chain

`PDD -> ChannelAgent Edge -> Channel Engine Host Control -> AI-CS -> Human Approval -> signed ExecutionAuthorization -> ChannelAgent Transport -> Receipt`

## Ownership

- ChannelAgent owns the device, isolated browser profile, PDD edge adapter boundary, encrypted 30-minute spool, desktop UI, signed V2.1 client, controlled transport, and receipt staging.
- Channel Engine owns registration, heartbeat, identity/store policy, approval delivery, execution authorization, lease, kill switch, immutable receipts, recovery, and V2.1 Host Control.
- AI-CS owns RBAC, store authorization, CustomerContext, product/SKU/order business data, RAG, LLM, Decision, long-term business storage, and business audit.

ChannelAgent must not package `channel_engine`, RAG, LLM, a knowledge store, or long-term chat/order data. Production Host Control must not mount Fake, Sandbox, Discovery, Pilot, or V1 routers.

## Legacy disposition

Duplicates are classified before movement. Current real-workflow experiments remain `ACTIVE_LEGACY`; old import paths stay for one RC cycle. Production composition is an explicit allowlist and excludes every legacy implementation. No unknown file is deleted.

## Hard activation gates

Real PDD activation remains denied until UNKNOWN receipts retain nullable facts and never retry, all LAN V1 routes return 404, signed V2.1 identity flows pass, and Selector Evidence is durable and page-fingerprint bound. Passing these gates means only `READY_FOR_CONTROLLED_PILOT`.
