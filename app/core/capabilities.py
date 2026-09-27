"""Capability Registry da Lumen — fundação da F0.

Catálogo declarativo de capacidades. Não executa capacidades, não concede
permissões e não altera políticas de segurança.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class CapabilityStatus(str, Enum):
    IMPLEMENTED = "IMPLEMENTED"
    PARTIAL = "PARTIAL"
    PLANNED = "PLANNED"
    EXPERIMENTAL = "EXPERIMENTAL"


class CapabilityRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class Capability:
    id: str
    name: str
    description: str
    status: CapabilityStatus
    risk: CapabilityRisk
    contracts: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("id", "name", "description"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.status, CapabilityStatus):
            raise ValueError("status must be CapabilityStatus")
        if not isinstance(self.risk, CapabilityRisk):
            raise ValueError("risk must be CapabilityRisk")
        if self.status is CapabilityStatus.IMPLEMENTED and not self.evidence:
            raise ValueError("IMPLEMENTED capability requires evidence reference")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "risk": self.risk.value,
            "contracts": list(self.contracts),
            "evidence": list(self.evidence),
            "dependencies": list(self.dependencies),
        }


class CapabilityRegistry:
    """Registro determinístico e somente-declarativo."""

    def __init__(self, capabilities: Iterable[Capability] = ()) -> None:
        self._items: dict[str, Capability] = {}
        for capability in capabilities:
            self.register(capability)

    def register(self, capability: Capability) -> None:
        if not isinstance(capability, Capability):
            raise TypeError("capability must be a Capability")
        if capability.id in self._items:
            raise ValueError(f"Capability already registered: {capability.id!r}")
        self._items[capability.id] = capability

    def get(self, capability_id: str) -> Capability:
        try:
            return self._items[capability_id]
        except KeyError as exc:
            raise KeyError(f"Unknown capability: {capability_id!r}") from exc

    def list(self) -> tuple[Capability, ...]:
        return tuple(self._items.values())

    def by_status(self, status: CapabilityStatus) -> tuple[Capability, ...]:
        return tuple(item for item in self._items.values() if item.status is status)

    def by_risk(self, risk: CapabilityRisk) -> tuple[Capability, ...]:
        return tuple(item for item in self._items.values() if item.risk is risk)

    def __len__(self) -> int:
        return len(self._items)


def build_baseline_registry() -> CapabilityRegistry:
    return CapabilityRegistry((
        Capability(
            id="conversation", name="Conversação",
            description="Interação textual através do Agent Core.",
            status=CapabilityStatus.IMPLEMENTED, risk=CapabilityRisk.LOW,
            contracts=("AIProvider", "Agent", "Memory"),
            evidence=("tests/test_agent.py", "tests/test_provider.py"),
        ),
        Capability(
            id="structured_memory", name="Memória estruturada",
            description="Persistência, busca, atualização e sanitização.",
            status=CapabilityStatus.IMPLEMENTED, risk=CapabilityRisk.MEDIUM,
            contracts=("MemoryRecord", "RecordStore", "MemorySystem"),
            evidence=("tests/test_memory_records.py", "tests/test_memory_system.py"),
        ),
        Capability(
            id="planning", name="Planejamento",
            description="Planos com dependências e guardrails.",
            status=CapabilityStatus.IMPLEMENTED, risk=CapabilityRisk.MEDIUM,
            contracts=("Planner", "Plan", "PlannedTask"),
            evidence=("tests/test_planner.py", "tests/test_planner_advanced_planning.py"),
        ),
        Capability(
            id="secure_filesystem", name="Filesystem confinado",
            description="Operações confinadas a workspaces autorizados.",
            status=CapabilityStatus.IMPLEMENTED, risk=CapabilityRisk.HIGH,
            contracts=("Tool", "ToolRegistry", "WorkspaceSandbox", "Audit"),
            evidence=("tests/test_filesystem_sandbox.py", "tests/test_filesystem_integration.py"),
        ),
        Capability(
            id="secure_terminal", name="Terminal controlado",
            description="Comandos sujeitos a política, allowlist e checkpoint.",
            status=CapabilityStatus.IMPLEMENTED, risk=CapabilityRisk.HIGH,
            contracts=("TerminalPolicy", "ToolRegistry", "Checkpoint", "Audit"),
            evidence=("tests/test_terminal_policy.py", "tests/test_terminal_integration.py"),
        ),
        Capability(
            id="computer_control", name="Computer Control",
            description="Controle com scopes, política e auditoria; cobertura ainda parcial.",
            status=CapabilityStatus.PARTIAL, risk=CapabilityRisk.HIGH,
            contracts=("ComputerControl", "CCScope", "CCPolicy", "CCAudit"),
            evidence=("tests/test_cc_policy_unit.py", "tests/test_cc_scopes_unit.py"),
        ),
        Capability(
            id="research", name="Research Engine",
            description="Pesquisa externa com coleta, síntese e verificação.",
            status=CapabilityStatus.PLANNED, risk=CapabilityRisk.MEDIUM,
            contracts=("ResearchEngine", "Source", "Provenance"),
        ),
        Capability(
            id="vision", name="Vision Provider",
            description="Interpretação visual estruturada.",
            status=CapabilityStatus.PLANNED, risk=CapabilityRisk.HIGH,
            contracts=("VisionProvider", "VisualObservation", "Grounding"),
        ),
        Capability(
            id="evolution", name="Lumen Evolution System",
            description="Medição, experimentação, benchmark e promoção.",
            status=CapabilityStatus.PLANNED, risk=CapabilityRisk.HIGH,
            contracts=("EvolutionEngine", "Experiment", "Benchmark", "PromotionGate"),
        ),
    ))
