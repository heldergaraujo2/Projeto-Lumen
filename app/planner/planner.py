"""Planner da Lumen (0.4 — fundação).

Transforma um pedido do usuário em um **plano estruturado** — sem
executar nada. O fluxo é:

    pedido → (memória relevante, se houver) → prompt de planejamento
    → provedor de IA (abstração :class:`AIProvider` — nunca um provider
    concreto) → resposta em JSON strict → validação → :class:`Plan`.

Garantias desta fundação:

- **Sem execução**: nenhuma tarefa é executada; todas nascem ``PENDING``.
- **Falha controlada**: JSON inválido/incompleto, dependências
  desconhecidas ou ciclos geram um plano ``FAILED`` com o motivo claro
  (nunca um traceback). Pré-condições ausentes do ambiente (provider sem
  API key/modelo/SDK) geram ``BLOCKED``.
- **Memória somente leitura**: quando um :class:`MemorySystem` (0.3) é
  fornecido, o Planner consulta ``recall()`` para enriquecer o contexto
  do planejamento — nunca grava nem duplica a memória.
- **Provider-agnóstico**: funciona com qualquer ``AIProvider``
  (mock/openai/gemini/groq/together) e respeita a troca em runtime.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from collections import deque
from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from app.ai.provider import (
    AIProvider,
    ContextMessage,
    MissingApiKeyError,
    ModelNotConfiguredError,
    ProviderDependencyError,
    ProviderError,
    user_message_for,
)
from app.ai.types import AIResponse
from app.planner.models import (
    Plan,
    PlanStatus,
    PlannedTask,
    _now_iso,
)

if TYPE_CHECKING:
    from app.memory.system import MemorySystem

logger = logging.getLogger("lumen.planner")


class PlannerError(RuntimeError):
    """Falha do módulo de planejamento."""


class InvalidPlanError(PlannerError):
    """A IA devolveu um plano inválido/interpretável (motivo na mensagem)."""


#: Pré-condições do ambiente que impedem planejar (não são erros do modelo):
#: sem chave, sem modelo ou sem SDK configurado.
_BLOCKING_ERRORS: tuple[type[ProviderError], ...] = (
    MissingApiKeyError,
    ModelNotConfiguredError,
    ProviderDependencyError,
)

_PLANNER_SYSTEM_PROMPT = """\
Você é o módulo de planejamento da Lumen. Sua ÚNICA função é transformar
o pedido do usuário em um plano estruturado de execução. NADA será
executado agora — você apenas planeja; não inclua comandos, código para
rodar nem ações diretas de arquivos/terminal.

Responda SOMENTE com um objeto JSON válido (sem markdown, sem cercas de
código, sem texto extra) exatamente no formato:
{
  "objective": "reformulação do objetivo em uma frase",
  "analysis": ["o que precisa ser analisado/verificado antes de executar"],
  "tasks": [
    {"id": 1, "description": "etapa clara e específica", "dependencies": []},
    {"id": 2, "description": "outra etapa", "dependencies": [1]}
  ]
}

Regras:
- "tasks": lista não vazia; ids únicos; ordem lógica de execução.
- "dependencies": ids de tarefas que devem terminar antes desta
  (lista vazia quando não houver); nunca crie dependências circulares.
- "analysis": pode ser lista vazia.
- Descreva etapas conceituais (entender requisitos, analisar estrutura,
  definir dados, implementar, verificar) — sem executar nada.
"""


@dataclass(frozen=True)
class ToolPlanResult:
    """Resultado do planejamento com ferramentas (0.6.3).

    ``kind``:

    - ``"plan"`` — plano ``READY`` com tarefas estruturadas
      (``tool``/``parameters`` validados contra a allowlist);
    - ``"conversation"`` — o pedido não exige ferramenta: segue o fluxo
      conversacional normal (nenhum plano, nada executado);
    - ``"invalid"`` — saída inválida do provedor (ferramenta inventada,
      parâmetros errados, JSON fora do protocolo, provedor falhou):
      falha **controlada** com o motivo em ``reason`` — nada executa.
    """

    kind: str
    plan: Plan
    reason: str | None = None


_TOOL_PLANNING_PROMPT = """\
Voce e o modulo de planejamento com ferramentas da Lumen. Analise o pedido
do usuario e responda SOMENTE com um objeto JSON valido (sem markdown, sem
cercas de codigo, sem texto extra), em um destes dois formatos:

1. Pedido puramente conversacional (nenhuma ferramenta e necessaria,
   ou o pedido nao pode ser atendido com as ferramentas disponiveis):
{"type": "conversation"}

2. Solicitacao de acao que pode ser atendida EXCLUSIVAMENTE com as
   ferramentas da allowlist abaixo:
{"type": "plan", "objective": "objetivo em uma frase",
 "analysis": ["o que verificar antes"],
 "tasks": [{"id": 1, "description": "etapa clara", "dependencies": [],
            "tool": "nome_exato_da_ferramenta", "parameters": {...}}]}

Regras:
- Use SOMENTE ferramentas da allowlist; nunca invente nomes de
  ferramentas, alias ou "ferramentas genericas".
- "parameters": exatamente os nomes e tipos listados para a ferramenta;
  nada de parametros extras.
- Caminhos sao RELATIVOS a raiz do workspace autorizado; nunca caminhos
  absolutos, ".." ou locais fora do workspace.
- Uma tarefa = uma ferramenta. Sem comandos de shell, codigo para rodar
  ou acoes fora das ferramentas listadas.
- NADA sera executado agora: toda execucao passa depois pelas camadas de
  seguranca (permissoes, workspace, checkpoint) que decidem o que roda.
- Campo OPCIONAL por tarefa: "success_criteria": ["criterio verificavel"]
  — apenas metadado informativo para o usuario (sem efeito na execucao).
- Data-flow (10B): um parametro de texto pode referenciar o resultado de
  uma tarefa anterior com "${Tn.data.<campo>}" (ex.: "${T1.data.content}").
  Regras: "n" deve ser o id de uma tarefa existente; a tarefa que usa a
  referencia DEVE declarar dependencia dela ("dependencies": [n]); maximo
  de 4 referencias por parametro. A validacao final dos campos exportaveis
  e feita na execucao (Executor) — o planejamento apenas planeja.

Allowlist de ferramentas disponiveis:
{catalog}
"""


@dataclass(frozen=True)
class PlannerLimits:
    """Guardrails do planejamento (10B) — exceder REJEITA o plano.

    Rejeição é sempre explícita (:class:`InvalidPlanError` ⇒ plano
    ``invalid``/``FAILED`` com o motivo): nada é truncado silenciosamente
    e nenhum plano parcial é executado. Defaults espelham
    :class:`~app.config.settings.Settings`.
    """

    max_tasks: int = 12
    max_dependency_depth: int = 6
    max_text_field_bytes: int = 16 * 1024
    max_dataflow_refs_per_param: int = 4


#: 10B — referência de data-flow em parâmetros (MESMA sintaxe do Executor;
#: o Planner valida forma/consistência de dependências, NÃO allowlist de
#: campos — a autoridade final permanece no Executor).
_DATAFLOW_REF = re.compile(r"\$\{T(\d+)\.data\.([A-Za-z_][A-Za-z0-9_]*)\}")


_REFINER_SYSTEM_PROMPT = """\
Voce e o REFINADOR CONSERVADOR de planos da Lumen. Recebe o pedido original
e o plano do estagio 1 (JSON). Devolva SOMENTE o JSON do plano completo
(mesmo schema), podendo alterar APENAS:
- "description" das tarefas (deixa-las mais claras e especificas);
- "analysis" do plano;
- "success_criteria" das tarefas (metadado informativo opcional);
- ADICIONAR dependencia de Tm para Tn SOMENTE quando a tarefa Tm usa
  "${Tn.data.<campo>}" em "parameters" e ainda nao depende de Tn.
PROIBIDO: trocar "tool", alterar "parameters", remover ou reordenar
dependencias, alterar ids, adicionar ou remover tarefas, mudar o objetivo.
Qualquer duvida: devolva o plano do estagio 1 inalterado.
"""


class Planner:
    """Cria planos estruturados a partir de pedidos (fundação 0.4).

    Args:
        provider: provedor de IA (abstração — injetado pelo Agent com o
            provider vigente, respeitando a troca em runtime).
        memory: sistema de memória 0.3 opcional — consultado em
            **somente leitura** (``recall``) para dar contexto ao
            planejamento; nunca é alterado.
        max_memory_hits: quantos registros de memória (no máximo) vão ao
            prompt de planejamento.
    """

    def __init__(
        self,
        provider: AIProvider,
        memory: "MemorySystem | None" = None,
        max_memory_hits: int = 5,
        catalog: dict | None = None,
        limits: PlannerLimits | None = None,
        refine_enabled: bool = False,
    ) -> None:
        if max_memory_hits < 1:
            raise ValueError("max_memory_hits deve ser >= 1.")
        self._provider = provider
        self._memory = memory
        self._max_memory_hits = int(max_memory_hits)
        #: Allowlist de ferramentas do planejamento (0.6.3). ``None`` =
        #: modo 0.4 clássico (tarefas descritivas, sem tool/parameters).
        self._catalog = catalog
        #: 10B — guardrails (rejeitam planos fora dos limites) e Stage 2
        #: opcional (refinador conservador com fallback obrigatório).
        self._limits = limits if limits is not None else PlannerLimits()
        self._refine_enabled = bool(refine_enabled)
        self._plan_counter = 0

    # -------------------------------------------------------------------- API
    def create_plan(
        self,
        objective: str,
        context: Sequence[ContextMessage] | None = None,
    ) -> Plan:
        """Planeja como atingir ``objective`` e devolve um :class:`Plan`.

        Nunca lança exceção de negócio: falhas voltam como planos
        ``FAILED``/``BLOCKED`` com o motivo em ``error``. Só lança
        :class:`ValueError` se o pedido for vazio (erro de programação
        do chamador).
        """
        if not isinstance(objective, str) or not objective.strip():
            raise ValueError("O objetivo do plano não pode ser vazio.")
        cleaned = objective.strip()

        self._plan_counter += 1
        plan_id = f"PLN-{self._plan_counter:04d}"
        draft = Plan(id=plan_id, objective=cleaned)  # status PLANNING

        # 10B (R5): limite de texto também para o objetivo — rejeição
        # explícita, nunca truncamento silencioso.
        try:
            self._reject_long_text("o objetivo", cleaned)
        except InvalidPlanError as exc:
            return self._finalize(
                draft, PlanStatus.FAILED, f"Plano inválido: {exc}",
            )

        system_prompt = self._build_system_prompt(cleaned)
        try:
            response = self._provider.chat(
                cleaned,
                [dict(item) for item in (context or [])],
                system_prompt=system_prompt,
            )
        except _BLOCKING_ERRORS as exc:
            return self._finalize(
                draft, PlanStatus.BLOCKED,
                f"Planejamento bloqueado: {user_message_for(exc)}",
            )
        except ProviderError as exc:
            friendly = user_message_for(exc)
            logger.error(
                "Provedor '%s' falhou ao planejar (%s): %s",
                self._provider.name, type(exc).__name__, exc,
            )
            return self._finalize(
                draft, PlanStatus.FAILED,
                f"O provedor de IA falhou durante o planejamento: {friendly}",
            )
        except Exception as exc:  # inesperado — controlado, sem traceback
            logger.exception("Erro inesperado no planejamento do plano %s.", plan_id)
            return self._finalize(
                draft, PlanStatus.FAILED,
                f"Erro inesperado durante o planejamento: {exc}",
            )

        if not isinstance(response, AIResponse):
            return self._finalize(
                draft, PlanStatus.FAILED,
                "O provedor devolveu um tipo inesperado "
                f"({type(response).__name__}); esperado AIResponse.",
            )
        content = (response.content or "").strip()
        if not content:
            return self._finalize(
                draft, PlanStatus.FAILED,
                "O provedor retornou uma resposta vazia — não foi possível "
                "criar o plano.",
            )

        try:
            analysis, tasks = self._parse_plan(content)
        except InvalidPlanError as exc:
            logger.warning("Plano %s inválido: %s", plan_id, exc)
            return self._finalize(
                draft, PlanStatus.FAILED,
                f"A IA devolveu um plano inválido: {exc}",
            )

        plan = self._finalize(draft, PlanStatus.READY, None, analysis, tasks)
        logger.info(
            "Plano %s criado (%s): %d tarefa(s) para o objetivo '%s'.",
            plan.id, plan.status.value, len(plan.tasks), cleaned[:80],
        )
        return plan

    # ------------------------------------------------- planejamento c/ tools
    def create_tool_plan(
        self,
        objective: str,
        context: Sequence[ContextMessage] | None = None,
    ) -> ToolPlanResult:
        """Planeja com a allowlist de ferramentas (0.6.3 — tool calling).

        Fluxo: pedido → prompt com a allowlist → provedor → JSON strict
        → validação de protocolo (:mod:`app.planner.catalog`) → plano
        READY com ``tool``/``parameters`` — ou falha controlada.

        - ``{"type": "conversation"}`` ⇒ ``kind="conversation"`` (nada
          é planejado nem executado — segue o fluxo de conversa);
        - resposta fora do protocolo, ferramenta fora da allowlist,
          parâmetros inválidos ou provedor falho ⇒ ``kind="invalid"``
          com o motivo em ``reason`` (**nunca** executa parcialmente);
        - exige ``catalog`` no construtor (senão é erro de programação).
        """
        if self._catalog is None:
            raise ValueError(
                "create_tool_plan exige um catálogo de ferramentas "
                "(Planner(catalog=...))."
            )
        if not isinstance(objective, str) or not objective.strip():
            raise ValueError("O objetivo do plano não pode ser vazio.")
        cleaned = objective.strip()

        self._plan_counter += 1
        plan_id = f"PLN-{self._plan_counter:04d}"
        draft = Plan(id=plan_id, objective=cleaned)  # status PLANNING

        # 10B (R5): limite de texto também para o objetivo — rejeição
        # explícita, nunca truncamento silencioso.
        try:
            self._reject_long_text("o objetivo", cleaned)
        except InvalidPlanError as exc:
            return self._tool_invalid(draft, f"Plano inválido: {exc}")

        system_prompt = self._build_tool_system_prompt(cleaned)
        try:
            response = self._provider.chat(
                cleaned,
                [dict(item) for item in (context or [])],
                system_prompt=system_prompt,
            )
        except _BLOCKING_ERRORS as exc:
            return ToolPlanResult(
                "invalid", self._finalize(
                    draft, PlanStatus.BLOCKED, None,
                ),
                f"Planejamento bloqueado: {user_message_for(exc)}",
            )
        except ProviderError as exc:
            friendly = user_message_for(exc)
            logger.error(
                "Provedor '%s' falhou ao planejar com ferramentas (%s): %s",
                self._provider.name, type(exc).__name__, exc,
            )
            return ToolPlanResult(
                "invalid", self._finalize(draft, PlanStatus.FAILED, None),
                f"O provedor de IA falhou durante o planejamento: {friendly}",
            )
        except Exception as exc:  # inesperado — controlado, sem traceback
            logger.exception(
                "Erro inesperado no planejamento (ferramentas) do %s.", plan_id
            )
            return ToolPlanResult(
                "invalid", self._finalize(draft, PlanStatus.FAILED, None),
                f"Erro inesperado durante o planejamento: {exc}",
            )

        content = (getattr(response, "content", "") or "").strip()
        if not content:
            return ToolPlanResult(
                "invalid", self._finalize(draft, PlanStatus.FAILED, None),
                "O provedor retornou uma resposta vazia — não foi possível "
                "criar o plano.",
            )

        # Classificação: conversa × plano (decisão do provedor, validada).
        try:
            head = self._extract_json(content)
        except InvalidPlanError as exc:
            return self._tool_invalid(draft, f"A IA devolveu um plano inválido: {exc}")
        kind = head.get("type")
        if kind == "conversation":
            logger.info(
                "Pedido conversacional (sem ferramenta) para '%s'.", cleaned[:80],
            )
            return ToolPlanResult("conversation", draft, None)
        if kind != "plan":
            return self._tool_invalid(
                draft,
                'resposta fora do protocolo ("type" deve ser "conversation" '
                'ou "plan")',
            )

        try:
            analysis, tasks = self._parse_plan(
                content, tool_mode=True,
                # 10B (R1): com Stage 2 ligado, a consistência deps↔refs
                # pode ser corrigida pelo refinador (adição de dep);
                # sem Stage 2 ela é exigida já no parse.
                defer_dataflow_consistency=self._refine_enabled,
            )
        except InvalidPlanError as exc:
            logger.warning("Plano com ferramentas %s inválido: %s", plan_id, exc)
            return self._tool_invalid(draft, f"A IA devolveu um plano inválido: {exc}")

        # 10B (R1): Stage 2 opcional — refinador CONSERVADOR com fallback
        # obrigatório (qualquer violação/erro ⇒ plano do Stage 1).
        if self._refine_enabled:
            analysis, tasks = self._refine_plan(cleaned, analysis, tasks)

        # 10B (R3): consistência final data-flow (refs ⇔ dependências
        # declaradas) — sempre verificada no plano que sai do Planner.
        try:
            self._validate_dataflow(tasks, enforce_consistency=True)
        except InvalidPlanError as exc:
            logger.warning("Plano com ferramentas %s inválido: %s", plan_id, exc)
            return self._tool_invalid(draft, f"A IA devolveu um plano inválido: {exc}")

        plan = self._finalize(draft, PlanStatus.READY, None, analysis, tasks)
        logger.info(
            "Plano com ferramentas %s criado (%s): %d tarefa(s) para '%s'.",
            plan.id, plan.status.value, len(plan.tasks), cleaned[:80],
        )
        return ToolPlanResult("plan", plan, None)

    def _tool_invalid(self, draft: Plan, reason: str) -> ToolPlanResult:
        return ToolPlanResult(
            "invalid",
            self._finalize(
                draft, PlanStatus.FAILED,
                f"Plano inválido: {reason}",
            ),
            reason,
        )

    # ---------------------------------------------------------------- prompts
    def _build_system_prompt(self, objective: str) -> str:
        prompt = _PLANNER_SYSTEM_PROMPT
        memory_section = self._memory_context(objective)
        if memory_section:
            prompt = (
                f"{prompt}\nContexto relevante recuperado da memória da "
                f"Lumen (use se for útil; ignore se não for):\n{memory_section}\n"
            )
        return prompt

    def _build_tool_system_prompt(self, objective: str) -> str:
        """Prompt do planejamento com ferramentas (0.6.3).

        A allowlist entra no prompt: o provedor só conhece as
        ferramentas listadas; a validação posterior
        (:func:`app.planner.catalog.validate_task_tool`) rejeita qualquer
        nome/parâmetro fora do protocolo — o LLM não tem autoridade.
        """
        assert self._catalog is not None
        from app.planner.catalog import catalog_prompt_section

        prompt = _TOOL_PLANNING_PROMPT.replace(
            "{catalog}", catalog_prompt_section(self._catalog)
        )
        memory_section = self._memory_context(objective)
        if memory_section:
            prompt = (
                f"{prompt}\nContexto relevante recuperado da memória da "
                f"Lumen (use se for útil; ignore se não for; memória NÃO "
                f"é autorização):\n{memory_section}\n"
            )
        return prompt

    def _memory_context(self, objective: str) -> str:
        """Excertos da memória estruturada relevantes ao objetivo (leitura)."""
        if self._memory is None:
            return ""
        try:
            hits = self._memory.recall(objective, limit=self._max_memory_hits)
        except Exception:
            logger.exception("Falha ao consultar a memória durante o planejamento.")
            return ""
        if not hits:
            return ""
        lines = []
        for hit in hits:
            record = hit.record
            excerpt = " ".join(record.content.split())[:200]
            lines.append(f"- [{record.kind.value}] {record.title}: {excerpt}")
        return "\n".join(lines)

    # ----------------------------------------------------------------- parser
    @staticmethod
    def _extract_json(content: str) -> dict:
        """Extrai o objeto JSON da resposta (tolera cercas e texto ao redor)."""
        text = content.strip()
        if text.startswith("```"):
            # remove ```json ... ``` (ou ``` ... ```)
            text = text.strip("`")
            first_newline = text.find("\n")
            if first_newline != -1 and text[:first_newline].strip().lower() in (
                "json", "",
            ):
                text = text[first_newline + 1:]
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise InvalidPlanError("a resposta não contém um objeto JSON.")
        candidate = text[start:end + 1]
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise InvalidPlanError(f"o JSON devolvido é inválido ({exc.msg}).") from exc
        if not isinstance(data, dict):
            raise InvalidPlanError("o JSON devolvido não é um objeto.")
        return data

    def _parse_plan(
        self, content: str, *, tool_mode: bool = False,
        defer_dataflow_consistency: bool = False,
    ) -> tuple[tuple[str, ...], tuple[PlannedTask, ...]]:
        """Valida a resposta da IA e converte em tarefas canônicas T1..Tn.

        ``tool_mode=True`` (0.6.3): cada tarefa DEVE trazer ``tool`` +
        ``parameters`` válidos contra a allowlist do catálogo — tarefa
        descritiva (sem ferramenta) é rejeitada neste modo.

        10B: aplica os guardrails de :class:`PlannerLimits` (nº de tarefas,
        profundidade de dependências, tamanho de campos de texto e nº de
        referências de data-flow por parâmetro — exceder REJEITA o plano)
        e valida a forma das referências ``${Tn.data.<campo>}``.
        ``defer_dataflow_consistency=True`` adia SOMENTE a exigência de
        dependência declarada (o Stage 2 pode adicioná-la); existência e
        limites continuam válidos imediatamente.
        """
        data = self._extract_json(content)

        raw_tasks = data.get("tasks")
        if not isinstance(raw_tasks, list) or not raw_tasks:
            raise InvalidPlanError("nenhuma tarefa foi planejada (\"tasks\" vazio).")

        # 1) Coleta descrições e ids originais (validação por item).
        descriptions: list[str] = []
        original_ids: list[str] = []
        for index, item in enumerate(raw_tasks, start=1):
            if not isinstance(item, dict):
                raise InvalidPlanError(f"a tarefa {index} não é um objeto.")
            description = item.get("description")
            if not isinstance(description, str) or not description.strip():
                raise InvalidPlanError(f"a tarefa {index} está sem descrição.")
            raw_id = item.get("id", index)
            try:
                original_ids.append(str(int(raw_id)))
            except (TypeError, ValueError):
                original_ids.append(str(raw_id).strip())
            descriptions.append(" ".join(description.split()))
            self._reject_long_text(f"a descrição da tarefa {index}",
                                   descriptions[-1])
            if tool_mode:
                from app.planner.catalog import validate_task_tool

                problem = validate_task_tool(
                    item.get("tool"), item.get("parameters"),
                    self._catalog or {},
                )
                if problem is not None:
                    raise InvalidPlanError(f"tarefa {index}: {problem}")

        if len(set(original_ids)) != len(original_ids):
            raise InvalidPlanError("há tarefas com ids duplicados.")

        # 10B (R5): teto de tarefas por plano — rejeição explícita.
        if len(raw_tasks) > self._limits.max_tasks:
            raise InvalidPlanError(
                f"o plano tem {len(raw_tasks)} tarefas "
                f"(máximo {self._limits.max_tasks})."
            )

        # 2) Mapeia ids originais → canônicos (T1..Tn pela ordem listada).
        canonical = {original: f"T{position}" for position, original in enumerate(original_ids, start=1)}

        tasks: list[PlannedTask] = []
        for index, item in enumerate(raw_tasks, start=1):
            dependencies: list[str] = []
            raw_deps = item.get("dependencies", []) or []
            if not isinstance(raw_deps, list):
                raise InvalidPlanError(f"dependências da tarefa {index} inválidas.")
            for dep in raw_deps:
                try:
                    dep_key = str(int(dep))
                except (TypeError, ValueError):
                    dep_key = str(dep).strip()
                if dep_key not in canonical:
                    raise InvalidPlanError(
                        f"a tarefa {index} depende de uma tarefa inexistente "
                        f"({dep_key!r})."
                    )
                dependencies.append(canonical[dep_key])
            task_kwargs = {}
            criteria_raw = item.get("success_criteria", []) or []
            if not isinstance(criteria_raw, list) or not all(
                isinstance(entry, str) and entry.strip()
                for entry in criteria_raw
            ):
                raise InvalidPlanError(
                    f"'success_criteria' da tarefa {index} deve ser uma "
                    "lista de textos."
                )
            criteria = tuple(" ".join(entry.split()) for entry in criteria_raw)
            for entry in criteria:
                self._reject_long_text(
                    f"'success_criteria' da tarefa {index}", entry,
                )
            task_kwargs["success_criteria"] = criteria
            if tool_mode:
                task_kwargs["tool"] = str(item["tool"]).strip()
                task_kwargs["parameters"] = dict(item["parameters"])
            tasks.append(
                PlannedTask(
                    id=canonical[original_ids[index - 1]],
                    description=descriptions[index - 1],
                    order=index,
                    dependencies=tuple(dependencies),
                    **task_kwargs,
                )
            )

        # 3) Rejeita ciclos de dependência (ordenação topológica — Kahn).
        Planner._ensure_acyclic(tasks)

        # 10B (R5): profundidade máxima de dependências (cadeia mais longa).
        depth = Planner._dependency_depth(tasks)
        if depth > self._limits.max_dependency_depth:
            raise InvalidPlanError(
                f"profundidade de dependências é {depth} "
                f"(máximo {self._limits.max_dependency_depth})."
            )

        # 10B (R3): forma das referências ${Tn.data.<campo>} — existência,
        # contagem por parâmetro e (salvo deferência p/ Stage 2) deps.
        self._validate_dataflow(
            tasks, enforce_consistency=not defer_dataflow_consistency,
        )

        analysis_raw = data.get("analysis", []) or []
        if not isinstance(analysis_raw, list) or not all(
            isinstance(item, str) and item.strip() for item in analysis_raw
        ):
            raise InvalidPlanError("\"analysis\" deve ser uma lista de textos.")
        analysis = tuple(" ".join(item.split()) for item in analysis_raw)
        for item in analysis:
            self._reject_long_text("\"analysis\"", item)

        return analysis, tuple(tasks)

    # ------------------------------------------------- 10B: guardrails/refino
    def _reject_long_text(self, label: str, text: str) -> None:
        """R5: campo de texto acima do limite REJEITA (nunca trunca)."""
        if len(text.encode("utf-8")) > self._limits.max_text_field_bytes:
            raise InvalidPlanError(
                f"{label} excede o limite de "
                f"{self._limits.max_text_field_bytes} bytes."
            )

    @staticmethod
    def _dependency_depth(tasks: list[PlannedTask]) -> int:
        """R5: comprimento da cadeia de dependências mais longa."""
        by_id = {task.id: task for task in tasks}
        memo: dict[str, int] = {}

        def depth_of(task_id: str) -> int:
            if task_id in memo:
                return memo[task_id]
            deps = by_id[task_id].dependencies
            memo[task_id] = 1 + max((depth_of(dep) for dep in deps), default=0)
            return memo[task_id]

        return max((depth_of(task.id) for task in tasks), default=0)

    @staticmethod
    def _param_strings(parameters: dict | None):
        """Valores de texto de ``parameters`` (inclui itens de listas)."""
        for value in (parameters or {}).values():
            if isinstance(value, str):
                yield value
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        yield item

    def _validate_dataflow(
        self, tasks: tuple[PlannedTask, ...] | list[PlannedTask],
        *, enforce_consistency: bool,
    ) -> None:
        """R3: valida referências ``${Tn.data.<campo>}`` do plano.

        Sintaxe/contagem/existência são SEMPRE válidas; a consistência
        (tarefa que referencia ``Tn`` deve depender de ``Tn``) é exigida
        quando ``enforce_consistency`` (o Stage 2 pode adicionar a
        dependência faltante antes da checagem final). O Planner NÃO
        valida allowlist de campos exportáveis — a autoridade final do
        data-flow permanece no Executor.
        """
        total = len(tasks)
        for task in tasks:
            for value in self._param_strings(task.parameters):
                references = _DATAFLOW_REF.findall(value)
                if not references:
                    continue
                if len(references) > self._limits.max_dataflow_refs_per_param:
                    raise InvalidPlanError(
                        f"parâmetro da tarefa {task.id} usa {len(references)} "
                        "referências de data-flow (máximo "
                        f"{self._limits.max_dataflow_refs_per_param})."
                    )
                for number, _field in references:
                    position = int(number)
                    if position < 1 or position > total:
                        raise InvalidPlanError(
                            f"a tarefa {task.id} referencia T{position}, que "
                            "não existe no plano."
                        )
                    referenced = f"T{position}"
                    if referenced == task.id:
                        raise InvalidPlanError(
                            f"a tarefa {task.id} não pode referenciar dados "
                            "dela mesma."
                        )
                    if enforce_consistency and referenced not in task.dependencies:
                        raise InvalidPlanError(
                            f"a tarefa {task.id} usa ${{{referenced}.data…}} "
                            "sem dependência declarada — referência de "
                            "data-flow exige dependência explícita."
                        )

    def _refine_plan(
        self, objective: str, analysis: tuple[str, ...],
        tasks: tuple[PlannedTask, ...],
    ) -> tuple[tuple[str, ...], tuple[PlannedTask, ...]]:
        """R1: Stage 2 — refinador CONSERVADOR com fallback obrigatório.

        Pode: melhorar description/analysis, adicionar success_criteria e
        adicionar dependência apenas para referências ``${Tn.data…}``
        sem dep. NÃO pode: trocar tool, alterar parameters, remover/reor-
        denar deps, alterar ids, adicionar/remover tarefas. Qualquer erro
        ou violação ⇒ devolve o plano do Stage 1 INTACTO.
        """
        stage1 = json.dumps({
            "type": "plan",
            "objective": objective,
            "analysis": list(analysis),
            "tasks": [{
                "id": int(task.id[1:]),
                "description": task.description,
                "dependencies": [int(dep[1:]) for dep in task.dependencies],
                "tool": task.tool,
                "parameters": task.parameters,
                **({"success_criteria": list(task.success_criteria)}
                   if task.success_criteria else {}),
            } for task in tasks],
        }, ensure_ascii=False)
        try:
            response = self._provider.chat(
                f"Pedido original:\n{objective}\n\nPlano do estagio 1:\n{stage1}",
                [],
                system_prompt=_REFINER_SYSTEM_PROMPT,
            )
            content = (getattr(response, "content", "") or "").strip()
            refined_data = self._extract_json(content)
            if refined_data.get("type") != "plan":
                raise InvalidPlanError("refino fora do protocolo.")
            refined_analysis, refined_tasks = self._parse_plan(
                json.dumps(refined_data, ensure_ascii=False),
                tool_mode=True,
                defer_dataflow_consistency=True,
            )
            problem = self._conservative_diff(tasks, refined_tasks)
            if problem is not None:
                raise InvalidPlanError(problem)
        except Exception as exc:  # fallback OBRIGATÓRIO: stage 1 intacto
            logger.warning("Stage 2 (refino) descartado — usando Stage 1: %s", exc)
            return analysis, tasks
        logger.info("Stage 2 (refino conservador) aplicado ao plano.")
        return refined_analysis, refined_tasks

    @staticmethod
    def _conservative_diff(
        original: tuple[PlannedTask, ...], refined: tuple[PlannedTask, ...],
    ) -> str | None:
        """Regras semânticas do refinador; devolve o problema ou ``None``."""
        if len(refined) != len(original):
            return "o refino mudou o número de tarefas."
        for before, after in zip(original, refined):
            if before.id != after.id or before.order != after.order:
                return f"o refino alterou ids/ordem (tarefa {before.id})."
            if before.tool != after.tool:
                return f"o refino trocou a ferramenta da tarefa {before.id}."
            if (before.parameters or {}) != (after.parameters or {}):
                return f"o refino alterou parâmetros da tarefa {before.id}."
            before_deps = set(before.dependencies)
            after_deps = set(after.dependencies)
            if before_deps - after_deps:
                return f"o refino removeu dependências da tarefa {before.id}."
            added = after_deps - before_deps
            if added:
                allowed = {
                    f"T{number}"
                    for value in Planner._param_strings(before.parameters)
                    for number, _field in _DATAFLOW_REF.findall(value)
                } - before_deps
                if not added <= allowed:
                    return (
                        f"o refino adicionou dependência indevida à tarefa "
                        f"{before.id}."
                    )
        return None

    @staticmethod
    def _ensure_acyclic(tasks: list[PlannedTask]) -> None:
        ids = {task.id for task in tasks}
        dependents: dict[str, list[str]] = {task_id: [] for task_id in ids}
        in_degree: dict[str, int] = {task_id: 0 for task_id in ids}
        for task in tasks:
            for dep in task.dependencies:
                dependents[dep].append(task.id)
                in_degree[task.id] += 1
        queue = deque(task_id for task_id, degree in in_degree.items() if degree == 0)
        visited = 0
        while queue:
            current = queue.popleft()
            visited += 1
            for dependent in dependents[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        if visited != len(tasks):
            raise InvalidPlanError(
                "as dependências formam um ciclo — o plano não pode ser "
                "ordenado."
            )

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _finalize(
        draft: Plan,
        status: PlanStatus,
        error: str | None,
        analysis: tuple[str, ...] = (),
        tasks: tuple[PlannedTask, ...] = (),
    ) -> Plan:
        return replace(
            draft, status=status, error=error, analysis=analysis,
            tasks=tasks, updated_at=_now_iso(),
        )


__all__ = [
    "Planner",
    "PlannerError",
    "InvalidPlanError",
]
