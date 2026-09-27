# Computer Control + Vision — Implementation Matrix

| Capability | Implementation | Status |
|---|---|---|
| Session authority | CCSessionManager | IMPLEMENTED |
| Total action budget | CCScope | IMPLEMENTED |
| Per-minute action budget | CCScope rolling window | IMPLEMENTED |
| Session duration | CCScope | IMPLEMENTED |
| Screen-region guard | CCScope + GroundingEngine | IMPLEMENTED |
| Structured target hierarchy | TargetResolver | IMPLEMENTED |
| Vision contract | VisionProvider | IMPLEMENTED |
| Local Ollama VLM adapter | OllamaVisionProvider | IMPLEMENTED |
| Configurable Qwen3-VL default | qwen3-vl:8b | IMPLEMENTED |
| Windows mouse/keyboard | WindowsComputerControlDriver | WINDOWS-ONLY |
| Screenshot capture | WindowsComputerControlDriver | WINDOWS-ONLY |
| Window enumeration/focus | WindowsComputerControlDriver | WINDOWS-ONLY |
| Windows UI Automation adapter | WindowsUIAutomation | WINDOWS-ONLY |
| OCR | provider contract | PENDING |
| Template matching | provider contract | PENDING |
| Screenshot redaction | policy only | PENDING |
| Dedicated CC checkpoint wiring | not yet in ToolsController | PENDING |
| Unreal-specific resolver | not yet implemented | PENDING |
| Real Windows smoke suite | requires Windows runner | PENDING |
| Grounding benchmark | not yet implemented | PENDING |

Windows-only implementation is not considered production-ready until real Windows
smoke tests and benchmarks pass.
