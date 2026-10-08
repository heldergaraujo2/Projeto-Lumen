"""Renderização de um :class:`FeaturePlan` para revisão humana (Fase 2).

O usuário aprova ou rejeita **lendo o plano**. Esta camada existe para que
a decisão seja informada: o que será criado, o que será executado, com que
riscos, e quais fontes de pesquisa fundamentam cada passo.

Nenhuma função aqui executa, escreve ou lê o disco.
"""
from __future__ import annotations

from app.planning.models import ArtifactKind, FeaturePlan


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def render_markdown(plan: FeaturePlan, *, max_content_preview: int = 0) -> str:
    """Renderiza o plano em markdown para exibição/aprovação.

    ``max_content_preview=0`` (default) **não** mostra o conteúdo dos
    arquivos — mostra só caminho, tipo e tamanho. Isso evita despejar
    milhares de linhas no terminal do usuário; a revisão de conteúdo é
    feita arquivo a arquivo, quando ele quiser.
    """
    lines: list[str] = []
    lines.append(f"# Plano {plan.plan_id}")
    lines.append("")
    lines.append(f"**Objetivo:** {plan.objective}")
    if plan.summary:
        lines.append("")
        lines.append(f"**Abordagem:** {plan.summary}")
    lines.append("")
    lines.append(
        f"**Estado:** {plan.approval.status.value}"
        + (f" · decidido em {plan.approval.decided_at}" if plan.approval.decided_at else "")
    )
    lines.append(
        f"**Digest:** `{plan.digest}` · gerado por {plan.provider or '?'}"
        + (f"/{plan.model}" if plan.model else "")
        + f" em {plan.created_at}"
    )

    if plan.artifacts:
        lines.append("")
        lines.append(f"## Arquivos ({len(plan.artifacts)})")
        lines.append("")
        for index, artifact in enumerate(plan.artifacts, start=1):
            size = len(artifact.content.encode("utf-8"))
            verb = "criar" if artifact.kind is ArtifactKind.CREATE else "sobrescrever"
            lines.append(f"{index}. **{verb}** `{artifact.path}` — {_format_bytes(size)}")
            if artifact.description:
                lines.append(f"   - {artifact.description}")
            if artifact.language:
                lines.append(f"   - linguagem: `{artifact.language}`")
            if max_content_preview > 0:
                preview = artifact.content[:max_content_preview]
                lines.append("")
                lines.append("   ```")
                for code_line in preview.splitlines():
                    lines.append(f"   {code_line}")
                if len(artifact.content) > max_content_preview:
                    lines.append("   … (conteúdo truncado na pré-visualização)")
                lines.append("   ```")

    if plan.commands:
        lines.append("")
        lines.append(f"## Comandos ({len(plan.commands)})")
        lines.append("")
        for index, command in enumerate(plan.commands, start=1):
            marker = " 🔨" if command.is_build else ""
            lines.append(f"{index}. `{' '.join(command.argv)}`{marker}")
            if command.description:
                lines.append(f"   - {command.description}")
            if command.cwd:
                lines.append(f"   - cwd: `{command.cwd}`")
            lines.append(f"   - timeout: {command.timeout_s}s")

    if plan.validation_steps:
        lines.append("")
        lines.append("## Como validar")
        lines.append("")
        for step in plan.validation_steps:
            lines.append(f"- {step}")

    if plan.risks:
        lines.append("")
        lines.append("## Riscos declarados")
        lines.append("")
        for risk in plan.risks:
            lines.append(f"- ⚠️ {risk}")

    if plan.research_refs:
        lines.append("")
        lines.append("## Fontes de pesquisa")
        lines.append("")
        for ref in plan.research_refs:
            lines.append(f"- {ref}")

    lines.append("")
    lines.append("---")
    lines.append(
        "**Nada foi executado.** Aprove ou rejeite este plano para prosseguir."
    )
    return "\n".join(lines)


def render_summary_line(plan: FeaturePlan) -> str:
    """Uma linha para a UI/CLI (ex.: em uma listagem de pendentes)."""
    return (
        f"{plan.plan_id} · {plan.approval.status.value} · "
        f"{len(plan.artifacts)} arquivo(s) · {len(plan.commands)} comando(s) · "
        f"digest {plan.digest} · {plan.objective[:60]}"
    )


__all__ = ["render_markdown", "render_summary_line"]
