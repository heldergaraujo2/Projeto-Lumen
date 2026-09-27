# F14 — Self-Diagnostics + Research for Improvement

F14 connects measured capability state to evidence-backed improvement proposals.

## Pipeline

```
Capability
  ↓
Measurements
  ↓
Self-Diagnostics
  ↓
Research Query
  ↓
Research Evidence
  ↓
Improvement Opportunity
  ↓
Improvement Plan
  ↓
F13 Laboratory / later phases
```

## Contracts

- Diagnostics consume supplied measurements and produce deterministic status/severity.
- Research consumes a caller-owned evidence provider; F14 does not itself grant network, browser, filesystem or execution authority.
- Every research item has source, claim, kind and relevance.
- Opportunities link evidence IDs back to a measured diagnostic gap.
- Improvement plans preserve baseline, risk and research sources.
- Healthy capabilities do not automatically generate improvement work.

## Security

F14 does not execute experiments, modify runtime code, call drivers, grant permissions, alter Policy/Sandbox/Checkpoint/Audit, or promote candidates.

Research is evidence, not authority. A research claim cannot directly change the runtime.

## Scope

F14 provides deterministic diagnostics and evidence-to-improvement planning. Actual experimental execution remains in future phases and must use the isolated F13 laboratory and existing security gates.


F14 validation note: high-risk classification is strictly below half the configured threshold; boundary values remain medium risk.
