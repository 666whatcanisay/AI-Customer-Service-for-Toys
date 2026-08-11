# Legacy pre-2.0 archive index

No runtime source has been physically removed in this RC.

- `ACTIVE_LEGACY`: `channel_agent.pdd_workspace`, `channel_agent.pdd_workspace_send`, and `channel_agent.assistant_bridge`. They remain in the source tree because earlier real-workflow experiments still reference them. They are excluded from the 2.0 production package.
- `COMPATIBILITY_SHIM`: V1 Agent client route support now lives only in `channel_agent.legacy_client_v1`. Historical tests must explicitly pass `allow_legacy_control=True`; the 2.0 production composition does not package this module and the Host app does not mount V1 routes.
- `ARCHIVE_READY`: `src/ai_cs_agent` and development-only Fake/Sandbox/Pilot entrypoints are excluded from production composition. They remain at their old paths for one full RC cycle; this directory records the decision rather than deleting them.

Unknown untracked assets are neither moved nor deleted. Physical archival may occur only after the 2.0 RC Synthetic and clean-checkout gates pass.
