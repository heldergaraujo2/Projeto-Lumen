"""Catálogo de ferramentas para o planejamento com tool calling (0.6.3).

Este módulo é **dados + validação de protocolo**, nada mais:

- descreve, em formato declarativo, as ferramentas **já existentes** na
  arquitetura (6 de filesystem + ``run_command``) que o Planner pode
  referenciar em tarefas estruturadas (``tool``/``parameters``);
- valida a saída do provedor (nomes/parâmetros/tipos) **antes** de o
  plano existir de fato — uma saída inválida vira falha controlada no
  :class:`~app.planner.planner.Planner`, nunca execução parcial.

Fonte de verdade **não** é este módulo: a autoridade final sobre o que
roda continua sendo a cadeia de execução (``ToolRegistry`` →
``PermissionManager`` → workspace/sandbox → checkpoints → tool). O
catálogo é uma allowlist de **protocolo** — o Planner não pode inventar
ferramentas porque só aceita nomes daqui, e este módulo, por sua vez,
só expõe ferramentas que a camada de tools já registra.

Não importa ``app.tools`` (o pacote do planner permanece agnóstico e
livre de código de execução — garantido por testes estáticos).
"""
from __future__ import annotations

from dataclasses import dataclass

#: Tipos aceitos nos parâmetros (validação estrita de protocolo).
_TYPE_NAMES = ("string", "integer", "array")


@dataclass(frozen=True)
class ParameterSpec:
    """Um parâmetro nomeado de uma ferramenta do catálogo."""

    name: str
    type: str          # "string" | "integer" | "array"
    required: bool
    description: str


@dataclass(frozen=True)
class ToolSpec:
    """Uma ferramenta que o Planner pode referenciar (allowlist)."""

    name: str
    description: str
    parameters: tuple[ParameterSpec, ...]
    terminal: bool = False   # run_command: exige terminal habilitado
    computer_control: bool = False  # ferramentas de automação do desktop (CC)


def _fs(name: str, description: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        parameters=(
            ParameterSpec(
                "path", "string", True,
                "Caminho RELATIVO à raiz do workspace autorizado "
                "(nunca absoluto, nunca com '..').",
            ),
        ),
    )


#: Allowlist completa: 8 de filesystem + 2 de terminal (run_command,
#: run_pytest — gated por include_terminal) + 1 de Computer Control
#: (cc_request_scope — gated por include_computer_control, CC-4).
TOOL_SPECS: tuple[ToolSpec, ...] = (
    _fs("list_directory", "Lista arquivos e subdiretórios de um diretório."),
    _fs("read_file", "Lê o conteúdo de um arquivo de texto (UTF-8)."),
    ToolSpec(
        name="write_file",
        description="Sobrescreve (ou cria) um arquivo de texto no workspace.",
        parameters=(
            ParameterSpec(
                "path", "string", True,
                "Caminho relativo ao workspace (nunca absoluto, nunca '..').",
            ),
            ParameterSpec("content", "string", True, "Conteúdo completo a gravar."),
        ),
    ),
    ToolSpec(
        name="create_file",
        description="Cria um arquivo novo (falha se o arquivo já existir).",
        parameters=(
            ParameterSpec(
                "path", "string", True,
                "Caminho relativo ao workspace (nunca absoluto, nunca '..').",
            ),
            ParameterSpec("content", "string", True, "Conteúdo completo do arquivo."),
        ),
    ),
    _fs("delete_file", "Apaga um arquivo do workspace (exige aprovação)."),
    _fs("file_exists", "Verifica se um arquivo existe no workspace."),
    ToolSpec(
        name="search_files",
        description=(
            "Busca um texto (literal, sem regex) nos arquivos de texto do "
            "workspace e devolve correspondências (arquivo, linha, coluna "
            "e trecho). Somente leitura."
        ),
        parameters=(
            ParameterSpec(
                "path", "string", True,
                "Diretório relativo ao workspace onde buscar "
                "(nunca absoluto, nunca '..').",
            ),
            ParameterSpec(
                "query", "string", True,
                "Texto a buscar (literal, sem regex; não vazio).",
            ),
        ),
    ),
    ToolSpec(
        name="edit_file",
        description=(
            "Edita um arquivo do workspace substituindo um trecho "
            "LITERAL por outro — o trecho deve ocorrer EXATAMENTE 1 vez "
            "no arquivo (0 ou mais de 1 = erro controlado, nada é "
            "escrito). Operação destrutiva: exige permissão WRITE e "
            "aprovação de checkpoint."
        ),
        parameters=(
            ParameterSpec(
                "path", "string", True,
                "Caminho relativo ao workspace (nunca absoluto, nunca '..').",
            ),
            ParameterSpec(
                "expected_old_text", "string", True,
                "Trecho literal exato a substituir (sem regex; deve ser "
                "único no arquivo).",
            ),
            ParameterSpec(
                "new_text", "string", True,
                "Texto substituto (literal, não vazio).",
            ),
        ),
    ),
    ToolSpec(
        name="run_command",
        description=(
            "Executa UM comando da allowlist do terminal, dentro do "
            "workspace, com timeout (todas as proteções do terminal "
            "continuam valendo)."
        ),
        parameters=(
            ParameterSpec("command", "string", True, "Nome do comando (sem shell)."),
            ParameterSpec(
                "args", "array", False,
                "Argumentos fixos do comando (lista de textos, sem operadores).",
            ),
            ParameterSpec(
                "cwd", "string", False,
                "Diretório de trabalho relativo ao workspace (default: raiz). "
                "O timeout vem da allowlist do terminal (não do plano).",
            ),
        ),
        terminal=True,
    ),
    ToolSpec(
        name="run_pytest",
        description=(
            "Roda a suíte pytest do workspace de forma estruturada "
            "(execução controlada, sem shell, saída limitada). Exige "
            "permissão TERMINAL e aprovação de checkpoint antes de "
            "executar."
        ),
        parameters=(
            ParameterSpec(
                "path", "string", True,
                "Diretório relativo ao workspace (ex.: tests ou mini_tests).",
            ),
            ParameterSpec(
                "k", "string", False,
                "Filtro -k do pytest (restrito pela tool).",
            ),
            ParameterSpec(
                "maxfail", "integer", False,
                "Interrompe após N falhas (1..10; default 1).",
            ),
            ParameterSpec(
                "timeout_s", "integer", False,
                "Timeout em segundos (10..600; default 60).",
            ),
        ),
        terminal=True,
    ),

    ToolSpec(
        name="cc_request_scope",
        description=(
            "Solicita um escopo de Computer Control (consentimento por sessão) "
            "para automação de desktop. MVP: apenas a ação 'screenshot'. "
            "O escopo é temporário (máx. 3600s) e limitado em número de ações."
        ),
        parameters=(
            ParameterSpec(
                "allowed_actions",
                "array",
                True,
                "Ações permitidas no escopo (MVP: apenas ['screenshot']).",
            ),
            ParameterSpec(
                "expires_in_s",
                "integer",
                True,
                "Duração do escopo em segundos (1..3600).",
            ),
            ParameterSpec(
                "max_actions_total",
                "integer",
                True,
                "Limite total de ações no escopo (> 0).",
            ),
            ParameterSpec(
                "max_actions_per_minute",
                "integer",
                True,
                "Limite de ações por minuto (> 0).",
            ),
            ParameterSpec(
                "app_name",
                "string",
                False,
                "Nome do aplicativo-alvo (um de app/processo/janela é obrigatório).",
            ),
            ParameterSpec("process_name", "string", False, "Nome do processo-alvo."),
            ParameterSpec(
                "window_title_pattern",
                "string",
                False,
                "Padrão do título da janela.",
            ),
        ),
        computer_control=True,
    ),
    ToolSpec(
        name="cc_screenshot",
        description=(
            "Captura um screenshot (somente metadados; sem bytes) usando um scope de "
            "Computer Control previamente concedido."
        ),
        parameters=(
            ParameterSpec("scope_id", "string", True, "ID do scope de Computer Control."),
        ),
        computer_control=True,
    ),

    ToolSpec(
        name="cc_mouse_move",
        description=(
            "Move o mouse de forma relativa (dx, dy) usando um scope de Computer Control previamente concedido. "
            "MVP: movimento pequeno; sem clique/teclado."
        ),
        parameters=(
            ParameterSpec("scope_id", "string", True, "ID do scope de Computer Control."),
            ParameterSpec("dx", "integer", True, "Delta X (pixels), inteiro em [-50..50]."),
            ParameterSpec("dy", "integer", True, "Delta Y (pixels), inteiro em [-50..50]."),
        ),
        computer_control=True,
    ),

    ToolSpec(
        name="cc_list_scopes",
        description="Lista os scopes de Computer Control ativos nesta sess?o (metadados-only).",
        parameters=(),
        computer_control=True,
    ),

    ToolSpec(
        name="cc_revoke_scope",
        description="Revoga (remove) um scope de Computer Control desta sess?o.",
        parameters=(
            ParameterSpec("scope_id", "string", True, "ID do scope de Computer Control."),
        ),
        computer_control=True,
    ),

    ToolSpec(
        name="cc_mouse_click",
        description=(
            "Clica com o mouse (bot?o esquerdo) no ponto atual do cursor usando um scope de Computer Control "
            "previamente concedido (MVP: 1 click; sem coordenadas; sem double click)."
        ),
        parameters=(
            ParameterSpec("scope_id", "string", True, "ID do scope de Computer Control."),
        ),
        computer_control=True,
    ),

    ToolSpec(
        name="cc_mouse_click_at",
        description=(
            "Move o mouse de forma relativa (dx, dy) e clica (bot?o esquerdo) usando um scope de Computer Control "
            "previamente concedido (MVP: movimento pequeno; 1 click)."
        ),
        parameters=(
            ParameterSpec("scope_id", "string", True, "ID do scope de Computer Control."),
            ParameterSpec("dx", "integer", True, "Delta X (pixels), inteiro em [-50..50]."),
            ParameterSpec("dy", "integer", True, "Delta Y (pixels), inteiro em [-50..50]."),
        ),
        computer_control=True,
    ),

    ToolSpec(
        name="cc_key_type",
        description=(
            "Digita texto usando um scope de Computer Control previamente concedido "
            "(MVP: texto curto; sem registrar o conte?do no audit)."
        ),
        parameters=(
            ParameterSpec("scope_id", "string", True, "ID do scope de Computer Control."),
            ParameterSpec("text", "string", True, "Texto a digitar (MVP: <= 80 chars, sem caracteres de controle)."),
        ),
        computer_control=True,
    ),

    ToolSpec(
        name="cc_double_click_and_type",
        description=(
            "Executa double-click (bot?o esquerdo) no ponto atual do cursor e em seguida digita texto. "
            "Pensado para 1 aprova??o (popup ENTER) sem mover o mouse."
        ),
        parameters=(
            ParameterSpec("scope_id", "string", True, "ID do scope de Computer Control."),
            ParameterSpec("text", "string", True, "Texto a digitar (MVP: <= 80 chars, sem caracteres de controle)."),
            ParameterSpec("open_delay_ms", "integer", False, "Espera ap?s abrir (100..3000 ms). Default 700."),
        ),
        computer_control=True,
    ),

    ToolSpec(
        name="cc_focus_window",
        description="Foca a janela-alvo (best-effort) usando window_title_pattern do scope.",
        parameters=(
            ParameterSpec("scope_id", "string", True, "ID do scope de Computer Control."),
        ),
        computer_control=True,
    ),

    ToolSpec(
        name="cc_wait_for_window",
        description="Espera a janela-alvo aparecer e ent?o a foca (best-effort) usando window_title_pattern do scope.",
        parameters=(
            ParameterSpec("scope_id", "string", True, "ID do scope de Computer Control."),
            ParameterSpec("timeout_s", "integer", False, "Timeout em segundos (1..120). Default 10."),
        ),
        computer_control=True,
    ),

    ToolSpec(
        name="cc_locate_template",
        description="Localiza um template dentro de um screenshot (offline, vis?o local) e retorna coordenadas.",
        parameters=(
            ParameterSpec("scope_id", "string", True, "ID do scope de Computer Control."),
            ParameterSpec("screenshot_artifact_ref", "string", True, "Caminho do PNG (artifact_ref) do cc_screenshot."),
            ParameterSpec("template_path", "string", True, "Caminho do PNG do template (recorte)."),
            ParameterSpec("threshold", "number", False, "Threshold (0..1]. Default 0.90."),
        ),
        computer_control=True,
    ),
)


def build_catalog(
    *, include_terminal: bool, include_computer_control: bool = False
) -> dict[str, dict]:
    """Allowlist de planejamento como dict serializável (para o prompt).

    ``include_terminal=False`` (default quando o terminal não está
    habilitado) omite ``run_command`` — o Planner simplesmente não o
    conhece; não há como planejar o que não está na lista.
    ``include_computer_control`` faz o mesmo para as ferramentas de
    automação do desktop (CC-4): hoje revela apenas ``cc_request_scope``
    (solicitação de escopo/consentimento); as ações de automação
    propriamente ditas entram em etapa futura.
    """
    catalog: dict[str, dict] = {}
    for spec in TOOL_SPECS:
        if spec.terminal and not include_terminal:
            continue
        if spec.computer_control and not include_computer_control:
            continue
        catalog[spec.name] = {
            "description": spec.description,
            "parameters": [
                {
                    "name": param.name,
                    "type": param.type,
                    "required": param.required,
                    "description": param.description,
                }
                for param in spec.parameters
            ],
        }
    return catalog


def spec_for(name: str) -> ToolSpec | None:
    """Spec completa de uma ferramenta (ou ``None`` se desconhecida)."""
    for spec in TOOL_SPECS:
        if spec.name == name:
            return spec
    return None


def catalog_prompt_section(catalog: dict[str, dict]) -> str:
    """Renderiza o catálogo para o system prompt do planejamento."""
    lines = []
    for name, info in catalog.items():
        params = ", ".join(
            f"{p['name']}: {p['type']}{' (obrigatório)' if p['required'] else ' (opcional)'}"
            for p in info["parameters"]
        ) or "sem parâmetros"
        lines.append(f"- {name} — {info['description']} [parâmetros: {params}]")
    return "\n".join(lines)


def _path_suspect(value: str) -> bool:
    """Caminho que tenta escapar do workspace (protocolo 0.6.3).

    Absoluto POSIX (``/…``), raiz de drive (``C:\…``), UNC (``\\…``) ou
    com componente ``..``. O sandbox da camada de tools continua sendo
    a defesa de execução — isto rejeita a tentativa já no planejamento
    (falha controlada, nada executa).
    """
    stripped = value.strip()
    if stripped.startswith(("/", "\\")):
        return True
    if ":" in stripped.split("/")[0].split("\\")[0]:
        return True  # drive/unidade (ex.: C:) antes do 1º separador
    return ".." in stripped


def validate_task_tool(
    tool: object, parameters: object, catalog: dict[str, dict]
) -> str | None:
    """Valida UMA tarefa estruturada contra a allowlist do protocolo.

    Devolve ``None`` quando válida, ou o **motivo** claro do problema
    (usado na falha controlada do Planner — nada é executado):

    - tool vazia/ausente ou não-texto;
    - tool fora da allowlist (o LLM não pode inventar ferramentas);
    - ``parameters`` ausente/não-objeto;
    - parâmetros desconhecidos (rejeitados);
    - parâmetros obrigatórios ausentes;
    - tipos errados (string não vazia / inteiro / lista de textos).

    Esta validação é de **protocolo** — não substitui nem enfraquece as
    validações de execução (permissões, sandbox, checkpoint), que rodam
    depois e de forma independente.
    """
    if not isinstance(tool, str) or not tool.strip():
        return "tarefa sem ferramenta designada (\"tool\" vazio ou ausente)"
    name = tool.strip()
    if name not in catalog:
        return (
            f"ferramenta '{name}' não está na allowlist do planejamento "
            "(o provedor não pode inventar ferramentas)"
        )
    if parameters is None:
        return f"tarefa com tool '{name}' sem parâmetros"
    if not isinstance(parameters, dict):
        return (
            f"parâmetros da tarefa com '{name}' devem ser um objeto "
            f"(recebido: {type(parameters).__name__})"
        )
    spec = spec_for(name)
    assert spec is not None  # name veio do catálogo
    known = {param.name for param in spec.parameters}
    unknown = sorted(set(parameters) - known)
    if unknown:
        return (
            f"parâmetro(s) desconhecido(s) para '{name}': "
            f"{', '.join(map(str, unknown))}"
        )
    for param in spec.parameters:
        if not param.required:
            continue
        if param.name not in parameters:
            return f"parâmetro obrigatório ausente em '{name}': '{param.name}'"
    for key, value in parameters.items():
        pname = str(key)
        pspec = next((p for p in spec.parameters if p.name == pname), None)
        if pspec is None:  # já coberto por "desconhecidos"
            continue
        if pspec.type == "string":
            if not isinstance(value, str) or not value.strip():
                return (
                    f"parâmetro '{pname}' de '{name}' deve ser texto "
                    "não vazio"
                )
            if pname == "path" and _path_suspect(value):
                return (
                    f"parâmetro 'path' de '{name}' deve ser um caminho "
                    "relativo ao workspace, sem '..' e sem caminho "
                    "absoluto"
                )
        elif pspec.type == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                return f"parâmetro '{pname}' de '{name}' deve ser inteiro"
        elif pspec.type == "array":
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                return (
                    f"parâmetro '{pname}' de '{name}' deve ser lista de "
                    "textos"
                )
    return None
