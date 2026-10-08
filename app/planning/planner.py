"""Gerador de planos de feature a partir de objetivo + pesquisa (Fase 2).

Fluxo::

    objetivo do usuário  +  blocos de pesquisa (Fase 1)
              ↓
        FeaturePlanner (prompt estruturado → LLM → JSON estrito)
              ↓
        FeaturePlan  (dados, NÃO executável)
              ↓
        ApprovalGate (Fase 2 — decisão do usuário)
              ↓
        Plan do LUMEN → ToolsController.run_plan (cadeia de segurança existente)

O provedor é qualquer :class:`~app.ai.provider.AIProvider` — funciona com
``mock`` (offline, para testes), Ollama, OpenAI, Gemini, Groq ou Together.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Sequence

from app.planning.models import (
    MAX_ARTIFACTS,
    MAX_COMMANDS,
    MAX_TEXT_CHARS,
    ArtifactKind,
    FeaturePlan,
    PlanArtifact,
    PlanCommand,
    PlanningError,
)

logger = logging.getLogger("lumen.planning")

PLAN_JSON_SCHEMA = """
{
  "summary": "1-3 frases explicando a abordagem",
  "artifacts": [
    {
      "path": "Source/MeuJogo/Private/InventoryComponent.cpp",
      "kind": "create",
      "description": "Implementa o componente de inventário",
      "language": "cpp",
      "content": "conteúdo COMPLETO do arquivo"
    }
  ],
  "commands": [
    {
      "argv": ["UnrealBuildTool", "-projectfiles", "-project=C:/Proj/Proj.uproject"],
      "description": "Regenera os project files",
      "cwd": "",
      "timeout_s": 600,
      "is_build": true
    }
  ],
  "validation_steps": ["Abrir o editor e confirmar que compila sem erros"],
  "risks": ["O caminho do engine pode variar"]
}
"""

PLANNING_SYSTEM_PROMPT = """Você é o planejador de implementação da Lumen, uma \
assistente que trabalha no PC do usuário.

Sua tarefa: transformar um OBJETIVO em um plano de implementação concreto e
executável, apoiado nas EVIDÊNCIAS DE PESQUISA fornecidas.

Regras obrigatórias:
1. Responda APENAS com um objeto JSON válido. Sem texto antes ou depois, sem cercas de código.
2. `artifacts[].path` é SEMPRE relativo à raiz do workspace, com barras "/".
   Nunca use caminho absoluto, nunca use "..", nunca use letra de unidade (C:).
3. `artifacts[].content` é o conteúdo COMPLETO do arquivo — não use
   marcadores como "..." ou "resto do código".
4. `commands[].argv` é uma LISTA de argumentos. Nunca use shell, nunca use
   "&&", "|", ">" ou ";". Cada item é um argumento literal.
5. Se não tiver certeza do caminho do engine, NÃO invente — descreva o
   comando de forma genérica e registre o risco em `risks`.
6. Cite nas descrições a evidência de pesquisa que fundamenta cada passo,
   no formato [1], [2] correspondendo às fontes numeradas.
7. Prefira poucos arquivos completos e corretos a muitos arquivos parciais.
8. Não invente APIs do Unreal. Se a evidência não cobrir algo, diga em `risks`.

Formato exato esperado:
""" + PLAN_JSON_SCHEMA


class FeaturePlanningError(RuntimeError):
    """Falha ao produzir um plano (provedor, JSON inválido ou plano inválido)."""


class FeaturePlanner:
    """Produz :class:`FeaturePlan` a partir de objetivo + evidência de pesquisa."""

    def __init__(self, provider, *, max_artifacts: int = MAX_ARTIFACTS) -> None:
        self._provider = provider
        self._max_artifacts = min(max_artifacts, MAX_ARTIFACTS)
        self._counter = 0

    # ------------------------------------------------------------------ API
    def create_plan(
        self,
        objective: str,
        *,
        research: Sequence[str] | None = None,
        extra_context: str = "",
    ) -> FeaturePlan:
        """Gera o plano. Nunca executa nada.

        Raises:
            ValueError: objetivo vazio (erro de programação do chamador).
            FeaturePlanningError: provedor falhou ou devolveu um plano
                estruturalmente inválido.
        """
        if not isinstance(objective, str) or not objective.strip():
            raise ValueError("O objetivo não pode ser vazio.")
        objective = objective.strip()

        self._counter += 1
        plan_id = f"FPL-{self._counter:04d}"

        user_prompt = self._build_user_prompt(objective, research, extra_context)
        try:
            response = self._provider.chat(
                user_prompt,
                context=None,
                system_prompt=self.system_prompt(),
            )
        except Exception as exc:  # provedor é fronteira externa
            raise FeaturePlanningError(
                f"falha ao consultar o provedor durante o planejamento: {exc}"
            ) from exc

        content = getattr(response, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise FeaturePlanningError("o provedor devolveu uma resposta vazia.")

        payload = self._extract_json(content)
        plan = self._build_plan(plan_id, objective, payload)
        plan.validate()
        logger.info(
            "Plano %s gerado: %d artefato(s), %d comando(s).",
            plan_id, len(plan.artifacts), len(plan.commands),
        )
        return plan

    @staticmethod
    def system_prompt() -> str:
        return PLANNING_SYSTEM_PROMPT

    # --------------------------------------------------------------- prompt
    def _build_user_prompt(
        self, objective: str, research: Sequence[str] | None, extra_context: str
    ) -> str:
        parts = [f"OBJETIVO DO USUÁRIO:\n{objective}\n"]
        if research:
            blocks = [block for block in research if block and block.strip()]
            if blocks:
                joined = "\n\n".join(blocks)
                if len(joined) > MAX_TEXT_CHARS * 4:
                    joined = joined[: MAX_TEXT_CHARS * 4] + "\n… (pesquisa truncada)"
                parts.append(
                    "EVIDÊNCIAS DE PESQUISA (numere as fontes como [1], [2]…):\n"
                    f"{joined}\n"
                )
        if extra_context.strip():
            parts.append(f"CONTEXTO ADICIONAL DO PROJETO:\n{extra_context.strip()}\n")
        parts.append(
            "Gere o plano de implementação em JSON, seguindo exatamente o formato definido."
        )
        return "\n".join(parts)

    # --------------------------------------------------------------- parser
    @staticmethod
    def _extract_json(content: str) -> dict:
        """Extrai o objeto JSON, tolerando cercas de código e texto ao redor."""
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            first_newline = text.find("\n")
            if first_newline != -1 and text[:first_newline].strip().lower() in ("json", ""):
                text = text[first_newline + 1:]
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise FeaturePlanningError("a resposta do provedor não contém um objeto JSON.")
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise FeaturePlanningError(
                f"o JSON devolvido pelo provedor é inválido ({exc.msg})."
            ) from exc
        if not isinstance(data, dict):
            raise FeaturePlanningError("o JSON devolvido não é um objeto.")
        return data

    # ---------------------------------------------------------------- build
    def _build_plan(self, plan_id: str, objective: str, payload: dict) -> FeaturePlan:
        raw_artifacts = payload.get("artifacts") or []
        raw_commands = payload.get("commands") or []
        if not isinstance(raw_artifacts, list):
            raise FeaturePlanningError("'artifacts' deve ser uma lista.")
        if not isinstance(raw_commands, list):
            raise FeaturePlanningError("'commands' deve ser uma lista.")
        if not raw_artifacts and not raw_commands:
            raise FeaturePlanningError(
                "o plano não contém artefatos nem comandos — nada a executar."
            )

        artifacts: list[PlanArtifact] = []
        for index, item in enumerate(raw_artifacts[: self._max_artifacts]):
            if not isinstance(item, dict):
                raise FeaturePlanningError(f"artifacts[{index}] deve ser um objeto.")
            kind_raw = str(item.get("kind", "create")).strip().lower()
            try:
                kind = ArtifactKind(kind_raw)
            except ValueError as exc:
                raise FeaturePlanningError(
                    f"artifacts[{index}].kind inválido: {kind_raw!r} (use 'create' ou 'write')"
                ) from exc
            content = item.get("content")
            if not isinstance(content, str):
                raise FeaturePlanningError(
                    f"artifacts[{index}] ('{item.get('path')}') não tem 'content' textual — "
                    "o conteúdo completo do arquivo é obrigatório."
                )
            artifacts.append(
                PlanArtifact(
                    path=str(item.get("path", "")).strip(),
                    content=content,
                    kind=kind,
                    description=str(item.get("description", ""))[:MAX_TEXT_CHARS],
                    language=str(item.get("language", ""))[:64],
                )
            )

        commands: list[PlanCommand] = []
        for index, item in enumerate(raw_commands[:MAX_COMMANDS]):
            if not isinstance(item, dict):
                raise FeaturePlanningError(f"commands[{index}] deve ser um objeto.")
            argv_raw = item.get("argv")
            if isinstance(argv_raw, str):
                raise FeaturePlanningError(
                    f"commands[{index}].argv deve ser uma LISTA de argumentos, "
                    f"não uma string (recebido: {argv_raw[:60]!r})."
                )
            if not isinstance(argv_raw, list):
                raise FeaturePlanningError(f"commands[{index}].argv deve ser uma lista.")
            timeout = item.get("timeout_s", 300)
            if isinstance(timeout, bool) or not isinstance(timeout, int):
                try:
                    timeout = int(timeout)
                except (TypeError, ValueError) as exc:
                    raise FeaturePlanningError(
                        f"commands[{index}].timeout_s deve ser inteiro."
                    ) from exc
            commands.append(
                PlanCommand(
                    argv=tuple(str(part) for part in argv_raw),
                    cwd=str(item.get("cwd", "") or "").strip(),
                    description=str(item.get("description", ""))[:MAX_TEXT_CHARS],
                    timeout_s=timeout,
                    is_build=bool(item.get("is_build", False)),
                )
            )

        validation = [
            str(step)[:MAX_TEXT_CHARS]
            for step in (payload.get("validation_steps") or [])
            if isinstance(step, (str, int, float)) and str(step).strip()
        ]
        risks = [
            str(risk)[:MAX_TEXT_CHARS]
            for risk in (payload.get("risks") or [])
            if isinstance(risk, (str, int, float)) and str(risk).strip()
        ]

        plan = FeaturePlan(
            plan_id=plan_id,
            objective=objective,
            summary=str(payload.get("summary", ""))[:MAX_TEXT_CHARS],
            artifacts=tuple(artifacts),
            commands=tuple(commands),
            validation_steps=tuple(validation),
            risks=tuple(risks),
            provider=getattr(self._provider, "name", ""),
            model=getattr(self._provider, "model_name", "") or "",
        )
        try:
            plan.validate()
        except PlanningError as exc:
            raise FeaturePlanningError(f"o plano gerado é inválido: {exc}") from exc
        return plan


def extract_research_blocks(search_results: Sequence[Any]) -> list[str]:
    """Normaliza resultados da Fase 1 em blocos de texto para o prompt.

    Aceita tanto :class:`~app.research.models.WebSearchResponse` quanto
    dicionários já serializados (``ToolResult.data``).
    """
    blocks: list[str] = []
    for item in search_results:
        if item is None:
            continue
        renderer = getattr(item, "as_context_block", None)
        if callable(renderer):
            blocks.append(renderer())
            continue
        if isinstance(item, dict):
            results = item.get("results") or []
            lines = [f"Resultados de pesquisa para: {item.get('query', '')}", ""]
            for index, result in enumerate(results, start=1):
                if not isinstance(result, dict):
                    continue
                lines.append(f"[{index}] {result.get('title', '')}")
                lines.append(f"    {result.get('url', '')}")
                if result.get("content"):
                    lines.append(f"    {result['content']}")
                lines.append("")
            blocks.append("\n".join(lines))
    return blocks


__all__ = [
    "FeaturePlanner",
    "FeaturePlanningError",
    "PLANNING_SYSTEM_PROMPT",
    "PLAN_JSON_SCHEMA",
    "extract_research_blocks",
]
