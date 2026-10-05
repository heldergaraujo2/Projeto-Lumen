"""Universal agent runtime integrations for Lumen.

The runtime is intentionally optional: Lumen keeps its native security and
planner stack when third-party agent SDKs are unavailable, while this package
can delegate open-ended tasks to proven agent runtimes when they are installed.
"""
from .universal import RuntimeResult, UniversalAgentRuntime

__all__ = ["RuntimeResult", "UniversalAgentRuntime"]
