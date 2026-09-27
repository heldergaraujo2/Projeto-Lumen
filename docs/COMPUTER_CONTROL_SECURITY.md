# Computer Control — Security Contract

Computer Control is a separate authority from CHAT, READ, WRITE and TERMINAL.

A Computer Control grant is explicit, session-only, scoped to a target, restricted
to an action set, bounded by total/per-minute/session limits, optionally
restricted to a screen region, revocable and never persisted by CCSessionManager.

Execution chain:
Goal -> action request -> PermissionManager(COMPUTER_CONTROL) -> CCScope ->
Policy -> driver -> Audit -> Verification.

The model never calls a Windows driver directly. Vision is informational. A VLM
may propose a target, but GroundingEngine validates confidence and bounds and the
scope validates the final point before execution.

Screenshots are sensitive artifacts. Audit stores references/metadata, not image
bytes. External vision Providers are disabled by default.

Recovery is bounded and cannot grant permissions, widen a scope or bypass a checkpoint.
Windows-native execution is isolated under app/computer_control/windows/.
