"""Camada de planejamento de feature (Fase 2).

Transforma ``objetivo + evidências de pesquisa`` em um
:class:`FeaturePlan` — uma lista concreta de arquivos a criar e comandos a
rodar — e o submete a **aprovação explícita do usuário** antes de qualquer
execução.

Fronteira de responsabilidade::

    app/research/   →  descobre COMO fazer   (Fase 1)
    app/planning/   →  decide O QUE fazer    (Fase 2 — este pacote)
    ApprovalGate    →  usuário autoriza      (Fase 2)
    app/mcp_server/ →  expõe tools ao LLM    (Fase 3)
    app/unreal_bridge/ → alcança o editor    (Fase 4)

Executar é responsabilidade da cadeia já existente do LUMEN
(``ToolsController.run_plan`` → permissões → sandbox → checkpoint →
auditoria). Este pacote **não** executa nada.
"""
from __future__ import annotations

from app.planning.approval import (
    ApprovalDecision,
    ApprovalGate,
    ApprovalResult,
    require_approved,
)
from app.planning.models import (
    MAX_ARTIFACTS,
    MAX_ARTIFACT_CONTENT_BYTES,
    MAX_COMMANDS,
    ApprovalRecord,
    ApprovalStatus,
    ArtifactKind,
    FeaturePlan,
    PlanArtifact,
    PlanCommand,
    PlanNotApprovedError,
    PlanningError,
)
from app.planning.planner import (
    FeaturePlanner,
    FeaturePlanningError,
    extract_research_blocks,
)
from app.planning.render import render_markdown, render_summary_line

__all__ = [
    "ApprovalDecision",
    "ApprovalGate",
    "ApprovalRecord",
    "ApprovalResult",
    "ApprovalStatus",
    "ArtifactKind",
    "FeaturePlan",
    "FeaturePlanner",
    "FeaturePlanningError",
    "MAX_ARTIFACTS",
    "MAX_ARTIFACT_CONTENT_BYTES",
    "MAX_COMMANDS",
    "PlanArtifact",
    "PlanCommand",
    "PlanNotApprovedError",
    "PlanningError",
    "extract_research_blocks",
    "render_markdown",
    "render_summary_line",
    "require_approved",
]
