"""MockProvider — respostas simuladas, sem nenhuma API externa.

Garante que a Lumen execute de ponta a ponta (UI, Agent Core, memória,
tarefas, permissões, logs) sem chaves de API nem rede, e permite rodar
todos os testes offline. Regras simples e determinísticas.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.ai.provider import AIProvider, ContextMessage
from app.ai.types import AIResponse, ResponseType

if TYPE_CHECKING:
    from app.config.settings import Settings


def _normalize(text: str) -> str:
    """Minúsculas sem acentos, para casar ``Olá``/``ola``/``OLÁ``."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


#: Marcador do prompt de planejamento com ferramentas (0.6.3): quando
#: presente no system prompt, o mock assume o papel do "LLM planejador"
#: de forma determinística (sem rede, sem não-determinismo).
_TOOL_PLANNING_MARKER = "planejamento com ferramentas"

#: Conectores sequenciais que separam duas ações em um pedido composto
#: ("crie X e depois leia X", "liste e em seguida leia Y"). O split
#: acontece na mensagem ORIGINAL — antes de qualquer extração — para que
#: o conteúdo de ``contendo:`` de uma tarefa não engula a tarefa
#: seguinte. Somente conectores EXPLÍCITOS de sequência (o "e" solto de
#: "crie X e salve Y" não conta: não é deterministicamente sequencial).
_SEQUENTIAL_SPLIT = re.compile(
    r"\s*(?:\be\s+depois\b|\be\s+ent[ãa]o\b|\be\s+em\s+seguida\b|"
    r"\be\s+a\s+seguir\b|\be\s+ap[óo]s\b|\bdepois\b|\bent[ãa]o\b|"
    r"\bem\s+seguida\b|\ba\s+seguir\b|\bap[óo]s\b)\s*",
    re.IGNORECASE,
)

_GREETING = re.compile(r"^(ola|oi|eae|opa|hey|hello|bom dia|boa tarde|boa noite)\b")
_WHO = re.compile(r"(quem (e|es|era) (voce|vc)|o que (e|es) (voce|vc)|seu nome|qual .*nome)")
_HELP = re.compile(r"(ajuda|help|o que .*pode fazer|quais .*comandos|como funciona)")
_TASKS = re.compile(r"(tarefa|task|planej|plano|projeto)")
_THANKS = re.compile(r"obrigad")
_BYE = re.compile(r"(tchau|adeus|ate (mais|logo)|falo)")
_VERSION = re.compile(r"(versao|version|atualiz)")


class MockProvider(AIProvider):
    """Provedor simulado da Lumen (respostas fixas em português)."""

    name = "mock"

    def __init__(self, settings: "Settings | None" = None) -> None:
        model = str(getattr(settings, "model", "") or "").strip()
        self._model = model or "lumen-mock"

    @property
    def model_name(self) -> str:
        return self._model

    # ------------------------------------------------- planejamento (0.6.3)
    def chat(
        self,
        message: str,
        context: Sequence[ContextMessage] | None = None,
        *,
        system_prompt: str | None = None,
        on_delta=None,
        max_tokens: int | None = None,
    ) -> AIResponse:
        """Sobrescreve o padrão para reconhecer o modo de planejamento.

        Com o system prompt do planejamento **com ferramentas** (marcado
        por :data:`_TOOL_PLANNING_MARKER`), produz a saída estruturada
        determinística do protocolo 0.6.3 (``{"type": ...}``). Nos demais
        casos delega ao comportamento simulado clássico (:meth:`generate`).
        """
        if system_prompt and _TOOL_PLANNING_MARKER in system_prompt:
            content = self._plan_with_tools(message, system_prompt)
        else:
            content = self.generate(message, context)
        if on_delta is not None:
            on_delta(content)
        return AIResponse(
            content=content,
            model=self._model,
            usage=None,
            finish_reason="stop",
            response_type=ResponseType.FINAL_RESPONSE,
        )

    def _plan_with_tools(self, message: str, system_prompt: str) -> str:
        """'Inteligência' determinística do planejamento (só simula o LLM).

        Regras (pt-BR, normalizadas): criar/escrever/ler/listar/apagar/
        existir + alvo; terminal somente se a allowlist do prompt listar
        ``run_command``. Pedidos compostos por conectores sequenciais
        ("crie X e depois leia X") viram planos MULTI-TAREFA com
        dependências encadeadas (T2 depende de T1, ...); pedidos simples
        continuam gerando exatamente uma tarefa. Qualquer outra coisa
        (inclusive pedidos vagos ou destrutivos sem alvo único) é tratada
        como CONVERSA — nunca como ferramenta inventada. A validação real
        (allowlist/permissões/sandbox/checkpoint) acontece depois, na
        cadeia de execução — CADA tarefa é validada individualmente.
        """
        actions = self._match_sequential_actions(message, system_prompt)
        if len(actions) >= 2:
            return json.dumps({
                "type": "plan",
                "objective": " e depois ".join(o for o, _t, _p in actions),
                "analysis": [],
                "tasks": [{
                    "id": index,
                    "description": objective,
                    "dependencies": [] if index == 1 else [index - 1],
                    "tool": tool,
                    "parameters": parameters,
                } for index, (objective, tool, parameters)
                  in enumerate(actions, start=1)],
            }, ensure_ascii=False)
        text = _normalize(message)
        plan = self._match_file_action(text, message)
        if plan is None and "- run_command" in system_prompt:
            plan = self._match_terminal_action(text)
        if plan is None:
            return json.dumps({"type": "conversation"}, ensure_ascii=False)
        objective, tool, parameters = plan
        return json.dumps({
            "type": "plan",
            "objective": objective,
            "analysis": [],
            "tasks": [{
                "id": 1,
                "description": objective,
                "dependencies": [],
                "tool": tool,
                "parameters": parameters,
            }],
        }, ensure_ascii=False)

    def _match_sequential_actions(self, message: str, system_prompt: str):
        """Ações de um pedido composto ("A e depois B") — uma por segmento.

        Divide a mensagem ORIGINAL em :data:`_SEQUENTIAL_SPLIT` e interpreta
        cada segmento de forma independente, com as MESMAS regras do
        pedido simples (arquivo primeiro; terminal só se a allowlist do
        prompt listar ``run_command``). Devolve uma lista com >= 2 ações
        ``(objetivo, tool, parâmetros)`` somente quando TODOS os
        segmentos resolvem para uma ação concreta — qualquer segmento
        vago devolve ``[]`` e o pedido inteiro cai no caminho clássico
        de tarefa única (compatibilidade total com a 0.6.6: o conteúdo
        de ``contendo:`` que cite um conector continua chegando inteiro
        ao matching clássico).
        """
        segments = [s for s in _SEQUENTIAL_SPLIT.split(message) if s.strip()]
        if len(segments) < 2:
            return []
        actions = []
        for segment in segments:
            text = _normalize(segment)
            action = self._match_file_action(text, segment)
            if action is None and "- run_command" in system_prompt:
                action = self._match_terminal_action(text)
            if action is None:
                return []  # segmento vago ⇒ não é pedido composto
            actions.append(action)
        return actions

    @staticmethod
    def _target_file(raw: str) -> str | None:
        """Nome de arquivo citado (com extensão) — alvo único e concreto.

        Opera sobre o texto ORIGINAL (maiúsculas/minúsculas preservadas).
        """
        match = re.search(
            r"(?:arquivo|ficheiro)\s+(?:chamado\s+|de\s+nome\s+)?"
            r"[\"']?([\w\-.]+\.[\w\-.]+)[\"']?",
            raw, re.IGNORECASE,
        )
        return match.group(1) if match else None

    @staticmethod
    def _content_of(raw: str) -> str | None:
        """Conteúdo após o marcador — conectores e nova linha tolerados.

        Aceita ``contendo:``, ``contendo exatamente:``, ``contendo o
        seguinte:``, ``contendo o texto:``, ``com o conteúdo:`` etc.
        (conectores seguros podem se combinar). O conteúdo pode começar
        na MESMA linha ou em uma NOVA linha (com linhas em branco no
        meio) e pode ter várias linhas — o texto interno é preservado;
        apenas espaços/linhas em branco das extremidades (e um par de
        aspas que envolva TODO o conteúdo) são removidos.
        """
        match = re.search(
            r"(?:contendo|conte[uú]do|com o conte[uú]do)"
            r"(?:\s+(?:exatamente|isso|o seguinte|o texto|o conte[uú]do|"
            r"este texto|essa frase|a seguinte mensagem))*"
            r"\s*:?\s*(.+)$",
            raw, re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return None
        value = match.group(1).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1].strip()  # aspas envolvendo todo o conteúdo
        return value or None

    def _match_file_action(self, text: str, raw: str):
        """(objetivo, tool, parâmetros) para ações de arquivo; senão None.

        ``text``: mensagem normalizada (decisão); ``raw``: original
        (extração fiel de caminho/conteúdo).
        """
        target = self._target_file(raw)
        if target is not None:
            content = self._content_of(raw)
            if re.search(r"\b(crie|cria|criar|gere|salve)\b", text) and content:
                return (
                    f"Criar o arquivo {target}",
                    "create_file",
                    {"path": target, "content": content},
                )
            if re.search(r"\b(escreva|escrever|sobrescreva|sobrescrever|grave)\b",
                         text) and content:
                return (
                    f"Gravar o arquivo {target}",
                    "write_file",
                    {"path": target, "content": content},
                )
            if re.search(r"\b(leia|ler|mostre|exiba|abra)\b", text):
                return (
                    f"Ler o arquivo {target}",
                    "read_file",
                    {"path": target},
                )
            if re.search(r"\b(apague|apagar|exclua|excluir|delete|deletar|"
                         r"remova|remover)\b", text):
                return (
                    f"Apagar o arquivo {target}",
                    "delete_file",
                    {"path": target},
                )
            if re.search(r"(existe|existe\?|verifique se|confirme se|"
                         r"checa se|cheque se)", text):
                return (
                    f"Verificar se o arquivo {target} existe",
                    "file_exists",
                    {"path": target},
                )
        if re.search(r"\b(liste|listar)\b.*\b(arquivos|diretorio|pasta|"
                     r"conte[uú]do do workspace)\b", text):
            return (
                "Listar os arquivos do workspace",
                "list_directory",
                {"path": "."},
            )
        return None

    @staticmethod
    def _match_terminal_action(text: str):
        """Terminal: 'rode o comando X' — política real decide depois."""
        match = re.search(
            r"(?:rode|rodar|execute|executar|executa)\s+(?:o\s+|um\s+)?"
            r"comando\s+([\w.\-]+)",
            text,
        )
        if not match:
            return None
        command = match.group(1)
        return (
            f"Executar o comando {command}",
            "run_command",
            {"command": command},
        )

    def generate(self, message: str, context: Sequence[ContextMessage] | None = None) -> str:
        text = _normalize(message)
        previous = len(context or [])

        if _GREETING.search(text):
            reply = "Olá! Eu sou a Lumen. Como posso ajudar?"
        elif _WHO.search(text):
            reply = (
                "Eu sou a Lumen, uma assistente de IA feminina em construção. "
                "Nesta versão 0.2 posso conversar usando um provedor de IA configurável "
                "(estou em modo simulado, sem rede)."
            )
        elif _HELP.search(text):
            reply = (
                "Hoje eu consigo conversar e guardar nossa conversa na memória local. "
                "Ainda não tenho acesso ao seu computador — sem arquivos, terminal, mouse ou teclado. "
                "Isso chega em versões futuras."
            )
        elif _TASKS.search(text):
            reply = (
                "Meu sistema de tarefas existe internamente (IDs como T-0001, status PENDING), "
                "mas nesta fase eu ainda não executo tarefas automaticamente — isso chega com o Planner (0.4)."
            )
        elif _THANKS.search(text):
            reply = "De nada! Sempre à disposição."
        elif _BYE.search(text):
            reply = "Até logo! Nossa conversa já está salva — podemos continuar depois."
        elif _VERSION.search(text):
            reply = (
                "Estou na versão 0.2 (cérebro real): já suporto provedores de IA configuráveis "
                "via LUMEN_PROVIDER, com timeout, retry e streaming."
            )
        else:
            context_note = f", além de {previous} mensagens anteriores nesta conversa" if previous else ""
            reply = (
                f'Recebi sua mensagem: "{message.strip()}". Estou em modo simulado '
                f"e guardei tudo na memória{context_note}."
            )

        return reply
