# Lumen — Autonomous Evolution Loop

## Purpose

The autonomous mission must be a goal-directed, evidence-driven, persistent loop.
The observed \`research <-> list_toolsets\` behavior showed that a planner needs
durable state outside the model context.

The progress controller records evidence, blocks repeated identical work, tracks
capability gaps, preserves research findings, and gives deterministic next-step
recommendations.

## Control model

OBJECTIVE -> GAP AUDIT -> RESEARCH/DISCOVERY -> HYPOTHESIS -> BOUNDED ACTION
-> OBSERVATION/TEST -> EVIDENCE -> VALIDATE -> NEXT GAP

Failure path:

FAILURE -> DIAGNOSE/RESEARCH -> BOUNDED CORRECTION -> RETEST

## Integration contract

Create one \`AutonomousProgressController\` per mission under:

\`data/evolution/autonomous_progress.json\`

Before an action:

\`controller.admit(action, fingerprint)\`

After an action:

\`controller.record(...)\`

Planner context:

\`controller.planner_context()\`

When the planner repeats itself or stagnates:

\`controller.recommend(available_actions, context=...)\`

For the first Unreal mission, the controller guides discovery toward:

list_toolsets -> describe_toolset -> observe_unreal -> unreal_call
-> verify -> research/evolve_code -> retest -> validated capability -> next gap

The controller never executes tools, providers, drivers, or code changes. Existing
permission, sandbox, checkpoint, audit, rollback, build, and promotion gates remain
authoritative.

## Completion invariant

\`done\` is not proof. The mission engine must require explicit validation evidence
for the capability set requested by the goal before marking the mission complete.

## Recovery invariant

Failures receive a bounded recovery budget. A failure should normally become:

failure -> diagnose/research -> correction -> test -> retry

Only exhausted recovery or an explicit safety block should lead to the existing
blocked state.

## Why this fixes the observed test

The old loop could repeatedly perform:

research -> list_toolsets -> research -> list_toolsets

without durable knowledge that those actions had already produced the same evidence.

The controller persists fingerprints, evidence, stagnation, gaps, findings and validated
capabilities. Once toolsets are known, the deterministic guardrail recommends
description/observation instead of repeating discovery.
