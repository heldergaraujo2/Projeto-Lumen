# F13 — Evolution Laboratory

## Status

F13 creates the isolated experimental environment for the Lumen Evolution System.

### Architecture

Stable runtime and experimental workspaces are separate:

```text
STABLE RUNTIME
   │
   │ no direct mutation
   ▼
EVOLUTION LAB
   ├── Workspace
   ├── Experiment
   ├── Change Record
   └── Candidate
```

### Workspace contract

Every workspace:

- belongs to one `EVOLUTION-XXXXXX`;
- lives below `evolution-lab/`;
- is not the stable runtime;
- cannot escape using absolute or `..` paths.

### Change contract

F13 records proposed changes but does not execute them. Stable runtime paths such as `app/`, `tests/` and `.github/` cannot be targeted by laboratory changes.

### Candidate isolation

A candidate can only be registered inside a workspace belonging to the same evolution.

### Lifecycle

F13 reuses the F12 ExperimentManager state machine. It does not create a second lifecycle authority.

### Security boundary

The laboratory has no methods for:

- executing drivers;
- granting Permission;
- altering Policy;
- bypassing Sandbox;
- approving Checkpoints;
- changing Audit;
- promoting candidates.

Promotion remains under the F12 PromotionManager and explicit human approval.

### Scope

F13 establishes the isolated laboratory and candidate/change contracts. It does not yet provide real code execution, automatic patching, model training, or automatic promotion. Those are future phases.
