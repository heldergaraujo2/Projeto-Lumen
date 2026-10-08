"""Modelos da camada de planejamento de feature (Fase 2).

Um :class:`FeaturePlan` é **dados**, não execução: descreve os arquivos a
criar e os comandos a rodar, sempre acompanhado de uma
:class:`ApprovalRecord`. Converter o plano para o formato executável do
LUMEN (:meth:`FeaturePlan.to_planner_plan`) **exige** aprovação explícita —
:class:`PlanNotApprovedError` caso contrário.

Isso preserva a hierarquia de autoridade já existente no projeto
(``app/core/bridge.py``): nenhuma camada nova pode encurtar o caminho
entre "o LLM propôs" e "o usuário autorizou".
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

#: Teto de bytes do conteúdo de um artefato (anti-DoS no plano).
MAX_ARTIFACT_CONTENT_BYTES = 256 * 1024
#: Teto de itens por plano.
MAX_ARTIFACTS = 40
MAX_COMMANDS = 40
MAX_VALIDATION_STEPS = 20
MAX_TEXT_CHARS = 4_000

#: Caminho relativo seguro: sem absoluto, sem '..', sem drive letter.
_SAFE_RELATIVE_PATH = re.compile(r"^(?!/)(?!.*\.\.)(?![A-Za-z]:)(?!\\)[^\x00]+$")


class PlanNotApprovedError(RuntimeError):
    """Tentativa de executar um plano que não foi aprovado pelo usuário."""


class PlanningError(ValueError):
    """Plano estruturalmente inválido."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArtifactKind(str, Enum):
    """Como o artefato entra no workspace."""

    CREATE = "create"   # arquivo novo — falha se já existir
    WRITE = "write"     # sobrescreve (ou cria)


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class PlanArtifact:
    """Um arquivo a criar/gravar, com o conteúdo completo.

    ``path`` é validado como **relativo e seguro** — o sandbox do LUMEN
    rejeitaria de qualquer forma, mas validar aqui faz o plano falhar
    antes de chegar perto do disco, com mensagem útil ao usuário.
    """

    path: str
    content: str
    kind: ArtifactKind = ArtifactKind.CREATE
    description: str = ""
    language: str = ""

    def validate(self) -> None:
        if not self.path or not self.path.strip():
            raise PlanningError("artefato exige 'path'")
        if not _SAFE_RELATIVE_PATH.match(self.path.strip()):
            raise PlanningError(
                f"caminho de artefato deve ser relativo e sem '..': {self.path!r}"
            )
        if self.content is None:
            raise PlanningError(f"artefato {self.path!r} exige 'content'")
        size = len(self.content.encode("utf-8"))
        if size > MAX_ARTIFACT_CONTENT_BYTES:
            raise PlanningError(
                f"artefato {self.path!r} excede {MAX_ARTIFACT_CONTENT_BYTES} bytes ({size})"
            )
        if not isinstance(self.kind, ArtifactKind):
            raise PlanningError(f"kind inválido em {self.path!r}: {self.kind!r}")

    @property
    def tool(self) -> str:
        """Nome da tool LUMEN que materializa este artefato."""
        return "create_file" if self.kind is ArtifactKind.CREATE else "write_file"

    def to_task_parameters(self) -> dict[str, Any]:
        return {"path": self.path.strip(), "content": self.content}

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind.value,
            "description": self.description,
            "language": self.language,
            "bytes": len(self.content.encode("utf-8")),
        }


@dataclass(frozen=True)
class PlanCommand:
    """Um comando a rodar (ex.: UnrealBuildTool, gerar project files).

    Armazenado como **argv** (lista), nunca como string de shell — o
    terminal do LUMEN executa sem shell e bloqueia operadores.
    """

    argv: tuple[str, ...]
    cwd: str = ""
    description: str = ""
    timeout_s: int = 300
    #: Verdadeiro quando o comando compila (UBT/build) — a UI destaca esses.
    is_build: bool = False

    def validate(self) -> None:
        if not self.argv:
            raise PlanningError("comando exige 'argv' não vazio")
        for part in self.argv:
            if not isinstance(part, str) or not part:
                raise PlanningError(f"argv inválido em {self.argv!r}")
        if not 1 <= self.timeout_s <= 3_600:
            raise PlanningError(f"timeout_s fora de 1..3600: {self.timeout_s}")
        if self.cwd and not _SAFE_RELATIVE_PATH.match(self.cwd.strip()):
            raise PlanningError(f"cwd deve ser relativo e sem '..': {self.cwd!r}")

    @property
    def program(self) -> str:
        return self.argv[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "argv": list(self.argv),
            "cwd": self.cwd,
            "description": self.description,
            "timeout_s": self.timeout_s,
            "is_build": self.is_build,
        }


@dataclass(frozen=True)
class ApprovalRecord:
    """Decisão do usuário sobre um plano."""

    plan_id: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_at: str | None = None
    note: str = ""
    #: Identificação de quem aprovou (ex.: ``"local-user"``). Nunca a senha.
    approved_by: str = ""

    @property
    def is_approved(self) -> bool:
        return self.status is ApprovalStatus.APPROVED

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "status": self.status.value,
            "decided_at": self.decided_at,
            "note": self.note,
            "approved_by": self.approved_by,
        }


@dataclass(frozen=True)
class FeaturePlan:
    """Plano de implementação de uma feature, pronto para aprovação.

    Imutável: aprovar produz uma **cópia** (:meth:`with_approval`), de modo
    que um plano pendente nunca é mutado no lugar.
    """

    plan_id: str
    objective: str
    summary: str = ""
    artifacts: tuple[PlanArtifact, ...] = ()
    commands: tuple[PlanCommand, ...] = ()
    validation_steps: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    #: Blocos de evidência de pesquisa usados como base (fontes citáveis).
    research_refs: tuple[str, ...] = ()
    approval: ApprovalRecord = field(default_factory=lambda: ApprovalRecord(plan_id=""))
    created_at: str = field(default_factory=_now_iso)
    provider: str = ""
    model: str = ""

    # ------------------------------------------------------------ validação
    def validate(self) -> None:
        if not self.plan_id.strip():
            raise PlanningError("plano exige 'plan_id'")
        if not self.objective.strip():
            raise PlanningError("plano exige 'objective'")
        if self.approval.plan_id and self.approval.plan_id != self.plan_id:
            raise PlanningError(
                f"aprovação pertence a outro plano ({self.approval.plan_id!r})"
            )
        if len(self.artifacts) > MAX_ARTIFACTS:
            raise PlanningError(f"plano excede {MAX_ARTIFACTS} artefatos")
        if len(self.commands) > MAX_COMMANDS:
            raise PlanningError(f"plano excede {MAX_COMMANDS} comandos")
        if len(self.validation_steps) > MAX_VALIDATION_STEPS:
            raise PlanningError(f"plano excede {MAX_VALIDATION_STEPS} passos de validação")
        for artifact in self.artifacts:
            artifact.validate()
        for command in self.commands:
            command.validate()
        paths = [a.path.strip() for a in self.artifacts]
        if len(paths) != len(set(paths)):
            raise PlanningError("plano declara o mesmo arquivo duas vezes")

    def __post_init__(self) -> None:
        if not self.approval.plan_id:
            object.__setattr__(
                self, "approval", replace(self.approval, plan_id=self.plan_id)
            )

    # ------------------------------------------------------------------ API
    @property
    def is_approved(self) -> bool:
        return self.approval.is_approved

    @property
    def is_empty(self) -> bool:
        return not self.artifacts and not self.commands

    @property
    def digest(self) -> str:
        """Hash determinístico do conteúdo aprovado.

        Serve para detectar se um plano foi alterado depois da aprovação:
        só o que foi revisado pode ser executado.
        """
        payload = {
            "objective": self.objective,
            "artifacts": [
                {"path": a.path, "content": a.content, "kind": a.kind.value}
                for a in self.artifacts
            ],
            "commands": [list(c.argv) for c in self.commands],
            "validation_steps": list(self.validation_steps),
        }
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def with_approval(self, record: ApprovalRecord) -> "FeaturePlan":
        """Devolve uma cópia com a decisão aplicada (nunca muta no lugar)."""
        if record.plan_id and record.plan_id != self.plan_id:
            raise PlanningError(
                f"aprovação {record.plan_id!r} não pertence ao plano {self.plan_id!r}"
            )
        updated = replace(self, approval=replace(record, plan_id=self.plan_id))
        updated.validate()
        return updated

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "objective": self.objective,
            "summary": self.summary,
            "digest": self.digest,
            "created_at": self.created_at,
            "provider": self.provider,
            "model": self.model,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "commands": [c.to_dict() for c in self.commands],
            "validation_steps": list(self.validation_steps),
            "risks": list(self.risks),
            "research_refs": list(self.research_refs),
            "approval": self.approval.to_dict(),
        }

    # ------------------------------------------------- conversão p/ execução
    def to_planner_plan(self):
        """Converte para :class:`app.planner.models.Plan` executável.

        **Exige aprovação.** É este o único caminho do planejamento para a
        execução; sem ``APPROVED`` levanta
        :class:`PlanNotApprovedError` e nada é criado.

        O plano resultante entra no pipeline já existente
        (``ToolsController.run_plan``) e continua passando por permissões,
        sandbox do workspace, checkpoints e auditoria — esta camada **não**
        encurta a cadeia de segurança.
        """
        if not self.is_approved:
            raise PlanNotApprovedError(
                f"plano {self.plan_id} está {self.approval.status.value}; "
                f"aprove antes de executar"
            )
        if self.is_empty:
            raise PlanningError(f"plano {self.plan_id} não tem artefatos nem comandos")

        from app.planner.models import PlannedTask, Plan, PlanStatus

        # Os pais de cada artefato viram tarefas ``create_directory``
        # ANTES do arquivo: ``create_file``/``write_file`` exigem que o
        # diretório pai já exista (``_ensure_parent`` em
        # app/tools/filesystem.py). Sem esta expansão, nenhum plano com
        # arquivos aninhados (o caso normal em C++) executaria.
        directories: list[str] = []
        for artifact in self.artifacts:
            parent = PurePosixPath(artifact.path.strip().replace("\\", "/")).parent
            candidate = "" if str(parent) in (".", "") else str(parent)
            if candidate and candidate not in directories:
                directories.append(candidate)

        tasks: list[PlannedTask] = []
        order = 0
        emitted: set[str] = set()
        for artifact in self.artifacts:
            parent = PurePosixPath(artifact.path.strip().replace("\\", "/")).parent
            candidate = "" if str(parent) in (".", "") else str(parent)
            if candidate and candidate not in emitted:
                emitted.add(candidate)
                order += 1
                tasks.append(
                    PlannedTask(
                        id=f"T{order}",
                        description=f"criar diretório {candidate}",
                        order=order,
                        tool="create_directory",
                        parameters={"path": candidate},
                    )
                )
            order += 1
            tasks.append(
                PlannedTask(
                    id=f"T{order}",
                    description=artifact.description
                    or f"{artifact.kind.value} {artifact.path}",
                    order=order,
                    tool=artifact.tool,
                    parameters=artifact.to_task_parameters(),
                )
            )
        for command in self.commands:
            order += 1
            tasks.append(
                PlannedTask(
                    id=f"T{order}",
                    description=command.description or " ".join(command.argv),
                    order=order,
                    tool="run_command",
                    parameters={
                        "command": command.program,
                        "args": list(command.argv[1:]),
                        **({"cwd": command.cwd} if command.cwd else {}),
                    },
                )
            )

        plan = Plan(
            id=self.plan_id,
            objective=self.objective,
            status=PlanStatus.READY,
            tasks=tuple(tasks),
        )
        # `Plan` (app/planner/models.py) é um dataclass congelado sem
        # `validate()` — a verificação de sanidade é feita aqui, no que
        # esta camada pode garantir antes de entregar o plano à execução.
        if not plan.tasks:
            raise PlanningError(f"plano {self.plan_id} produziu zero tarefas executáveis")
        orders = [task.order for task in plan.tasks]
        if orders != list(range(1, len(orders) + 1)):
            raise PlanningError(
                f"plano {self.plan_id} tem ordenação de tarefas inválida: {orders}"
            )
        for task in plan.tasks:
            if not task.tool:
                raise PlanningError(
                    f"plano {self.plan_id}: tarefa {task.id} não designa ferramenta"
                )
        return plan


__all__ = [
    "ApprovalRecord",
    "ApprovalStatus",
    "ArtifactKind",
    "FeaturePlan",
    "MAX_ARTIFACTS",
    "MAX_ARTIFACT_CONTENT_BYTES",
    "MAX_COMMANDS",
    "MAX_TEXT_CHARS",
    "MAX_VALIDATION_STEPS",
    "PlanArtifact",
    "PlanCommand",
    "PlanNotApprovedError",
    "PlanningError",
]
