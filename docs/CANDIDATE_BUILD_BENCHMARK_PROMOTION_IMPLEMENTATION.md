# F15 — Candidate Build + Benchmark + Promotion

## Objective

F15 closes the path from an isolated evolution candidate to a promotion decision backed by build evidence, benchmark evidence, regression detection and security review.

## Pipeline

```
F14 IMPROVEMENT PLAN
       ↓
F13 LAB CANDIDATE
       ↓
BUILD EVIDENCE
       ↓
BENCHMARK SUITE
       ↓
REGRESSION CHECK
       ↓
SECURITY REVIEW
       ↓
PROMOTION ASSESSMENT
       ↓
PROMOTION_PENDING
       ↓
EXPLICIT HUMAN APPROVAL
       ↓
PROMOTED (METADATA STATE)
```

## Components

- `BuildEvidence` — immutable record of a caller-owned build result, artifacts and test evidence.
- `CandidateBuilder` — validates/records build evidence; it does not invoke compilers or processes.
- `BenchmarkSuite` — validates candidate identity, metric evidence and minimum sample size.
- `CandidateBenchmark` — delegates deterministic regression detection to the F12 engine.
- `PromotionAssessment` — combines build, benchmark/regression and security results.
- `PromotionGate` — bounded submission, explicit human approval, rejection and metadata-only promotion.

## Promotion conditions

A candidate cannot enter `PROMOTION_PENDING` unless:

1. build succeeded;
2. successful build has artifact evidence;
3. successful build has test evidence;
4. benchmark suite is valid;
5. no benchmark regression exceeds tolerance;
6. security review passes;
7. high-risk changes have explicit human approval.

Approval is never inferred from benchmark score.

## Security

F15 does not:

- invoke a compiler, process, browser or driver;
- deploy files;
- modify the stable runtime;
- grant permissions;
- alter Policy/Sandbox/Checkpoint/Audit;
- bypass protected components;
- infer human approval.

`promote_record()` changes only the candidate's registry state to `PROMOTED`. Physical deployment remains outside this contract and must use the existing security architecture.

## Rejection and rollback

Failed assessment can be rejected and the candidate enters `REJECTED`. Existing F12 `RollbackManager` remains the source for rollback records; F15 does not perform physical rollback.

## Evidence

F15 tests cover build validation, benchmark identity/sample validation, regression blocking, protected-component blocking, high-risk human approval, bounded promotion lifecycle, rejection, and absence of execution surfaces.
