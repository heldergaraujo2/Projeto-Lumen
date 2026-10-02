# Lumen Unified Operational Brain

## Purpose

F34 turns the previously separate evolution capabilities into one runtime-facing
cognitive control plane.

The central object is `OperationalBrain`. It combines:

- persistent mission identity and objective;
- CognitiveFusion memory/world/capability/research layers;
- deterministic anti-stagnation progress control;
- goal-directed action selection;
- bounded failure recovery;
- experience-based learning;
- capability validation;
- promotion gates;
- a complete structured reasoning context for the local provider.

## Runtime loop

```text
OBJECTIVE
  -> ORIENT
  -> OBSERVE / DISCOVER
  -> IDENTIFY GAP
  -> RESEARCH
  -> LEARN
  -> HYPOTHESIS
  -> EXPERIMENT / TOOL
  -> ACT
  -> VALIDATE
  -> REMEMBER
  -> REASSESS
  -> NEXT GAP
```

Failure is a first-class transition:

```text
FAIL
  -> RECOVER
  -> RESEARCH / DIAGNOSE
  -> CORRECT
  -> RETEST
```

Recovery is bounded and persistent. Exhausting the recovery budget produces
`BLOCKED` instead of an infinite self-modification loop.

## Provider role

The local provider is the reasoning engine, not the source of truth.

`OperationalBrain.reasoning_context()` gives the provider a structured view of
objective, mission state, world facts, capability gaps, research, tools,
hypotheses, lessons, recent evidence and deterministic progress state.

The provider may propose a plan, but the deterministic brain and existing
security/promotion gates remain authoritative.

## Persistence

The brain persists:

- `operational_brain.json`;
- `cognitive_fusion_snapshot.json`;
- the existing autonomous progress state.

A restart therefore resumes the same mission rather than starting a fresh
conversation.

## Safety invariant

F34 does **not** grant unrestricted permissions and does not bypass existing
F12-F32 security, benchmark, rollback or promotion controls.

The architectural goal is autonomy inside pre-authorized boundaries, with
evidence and recovery rather than blind self-modification.

## Integration contract

An autonomous runtime should perform:

1. instantiate `OperationalBrain` for the persistent mission;
2. provide the current available tool/actions and live observations;
3. call `decide()`;
4. execute the selected action through the existing broker/policy layer;
5. feed the result through `execute()`;
6. on failure call `recover()` and continue with the next decision;
7. validate capabilities only with concrete evidence;
8. stop only when the objective has external validation.

This makes the brain the **single cognitive control plane** while leaving actual
tool execution in the existing governed runtime.
