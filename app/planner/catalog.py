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
    web_search: bool = False  # web_search: exige provedor de busca configurado
    unreal: bool = False     # unreal_*: exige ponte com o editor habilitada


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


#: Allowlist completa (10 ferramentas já existentes — nada novo foi criado).
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
    ToolSpec(
        name="create_directory",
        description=(
            "Cria um diretório no workspace (inclusive pais ausentes). "
            "Use ANTES de criar arquivos em pastas que ainda não existem."
        ),
        parameters=(
            ParameterSpec(
                "path", "string", True,
                "Caminho relativo do diretório (nunca absoluto, nunca '..').",
            ),
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
        name="web_search",
        description=(
            "Pesquisa na web e devolve resultados com título, URL e trecho. "
            "Use ANTES de planejar uma implementação para descobrir como fazer."
        ),
        parameters=(
            ParameterSpec("query", "string", True, "Texto da busca."),
            ParameterSpec(
                "max_results", "integer", False,
                "Quantidade de resultados (1..10; default 5).",
            ),
        ),
        web_search=True,
    ),
    # ---------------------------------------------------------------- Unreal
    # Fase 4: as ferramentas da ponte com o editor. Ficam FORA do catálogo
    # por padrão — um projeto sem Unreal aberto não deve ver ferramentas que
    # só sabem falhar. `unreal: True` é o marcador que ToolsController usa
    # para incluí-las apenas quando enable_unreal_bridge() foi chamado.
    ToolSpec(
        name="unreal_get_info",
        description=(
            "Verifica a conexão com o Unreal Editor e lista as rotas da Remote "
            "Control API. Use SEMPRE antes das outras ferramentas unreal_*."
        ),
        parameters=(),
        unreal=True,
    ),
    ToolSpec(
        name="unreal_describe_object",
        description=(
            "Descreve um objeto do Unreal Editor (propriedades e funções com "
            "tipos). Use para descobrir nomes REAIS antes de set_property/call."
        ),
        parameters=(
            ParameterSpec(
                "object_path", "string", True,
                "Caminho do UObject, ex.: "
                "'/Game/Maps/Mapa.Mapa:PersistentLevel.MeuAtor'.",
            ),
        ),
        unreal=True,
    ),
    ToolSpec(
        name="unreal_search_assets",
        description=(
            "Busca assets no Content Browser pelo nome e devolve o caminho "
            "exato (ex.: '/Game/Blueprints/BP_Ator.BP_Ator')."
        ),
        parameters=(
            ParameterSpec("query", "string", True, "Texto a procurar ('' = tudo)."),
            ParameterSpec(
                "class_names", "array", False,
                "Filtra por classe, ex.: ['Blueprint', 'StaticMesh'].",
            ),
            ParameterSpec(
                "package_paths", "array", False,
                "Filtra por pasta, ex.: ['/Game/Blueprints'].",
            ),
        ),
        unreal=True,
    ),
    ToolSpec(
        name="unreal_set_property",
        description=(
            "Define uma propriedade de um objeto do Unreal Editor (Remote "
            "Control API pura). A propriedade precisa ser pública, sem "
            "BlueprintGetter/Setter, e EditAnywhere/BlueprintVisible."
        ),
        parameters=(
            ParameterSpec("object_path", "string", True, "Caminho do UObject."),
            ParameterSpec("property_name", "string", True, "Nome C++ da propriedade."),
            ParameterSpec(
                "value", "string", True,
                "Novo valor como texto ('2', 'true', '{\"X\":1,\"Y\":2,\"Z\":3}').",
            ),
        ),
        unreal=True,
    ),
    ToolSpec(
        name="unreal_call_function",
        description=(
            "Chama uma função de um objeto do Unreal Editor (Remote Control API "
            "pura). A função precisa ser chamável por Blueprint."
        ),
        parameters=(
            ParameterSpec("object_path", "string", True, "Caminho do UObject."),
            ParameterSpec("function_name", "string", True, "Nome C++ da função."),
            ParameterSpec(
                "parameters_json", "string", False,
                "Parâmetros em JSON (vazio = nenhum).",
            ),
        ),
        unreal=True,
    ),
    ToolSpec(
        name="unreal_create_blueprint_class",
        description=(
            "Cria uma classe Blueprint no Content Browser. EXIGE o Python "
            "Editor Script Plugin habilitado — a Remote Control API não tem "
            "rota para criar assets."
        ),
        parameters=(
            ParameterSpec("asset_name", "string", True, "Nome, ex.: 'BP_Inventario'."),
            ParameterSpec(
                "package_path", "string", False,
                "Pasta no Content Browser (default '/Game/Blueprints').",
            ),
            ParameterSpec(
                "parent_class", "string", False,
                "Classe pai (default 'Actor'; use 'ActorComponent' p/ componente).",
            ),
        ),
        unreal=True,
    ),
    ToolSpec(
        name="unreal_add_component",
        description=(
            "Adiciona um componente a um Blueprint existente. EXIGE o Python "
            "Editor Script Plugin e o transporte 'python' ou 'auto'."
        ),
        parameters=(
            ParameterSpec(
                "blueprint_path", "string", True,
                "Caminho do asset, ex.: '/Game/Blueprints/BP_Ator.BP_Ator'.",
            ),
            ParameterSpec(
                "component_class", "string", True,
                "Classe do componente, ex.: 'StaticMeshComponent'.",
            ),
            ParameterSpec(
                "component_name", "string", False,
                "Nome do componente (vazio = o editor escolhe).",
            ),
        ),
        unreal=True,
    ),
)


def build_catalog(
    *,
    include_terminal: bool,
    include_web_search: bool = False,
    include_unreal: bool = False,
) -> dict[str, dict]:
    """Allowlist de planejamento como dict serializável (para o prompt).

    ``include_terminal=False`` (default quando o terminal não está
    habilitado) omite ``run_command``/``run_pytest``. Do mesmo modo,
    ``include_web_search=False`` (default quando nenhum provedor de
    busca está configurado) omite ``web_search`` e ``include_unreal=False``
    (default quando não há ponte com o editor) omite as ``unreal_*`` — o
    Planner simplesmente não as conhece; não há como planejar o que não
    está na lista.
    """
    catalog: dict[str, dict] = {}
    for spec in TOOL_SPECS:
        if spec.terminal and not include_terminal:
            continue
        if spec.web_search and not include_web_search:
            continue
        if spec.unreal and not include_unreal:
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
