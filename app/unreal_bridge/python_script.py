"""Geração de código Python executado dentro do Unreal Editor (Fase 4).

Por que este módulo existe: a Remote Control API **não tem rota para criar
assets** (achado da Fase -1, confirmado contra a referência HTTP oficial —
a lista de rotas de ``/remote/info`` é completa e não inclui criação de
asset). Toda operação que cria algo novo no Content Browser precisa
executar Python dentro do editor, via Python Editor Script Plugin.

Consequência prática, dita sem rodeios: ``unreal_create_blueprint_class`` e
``unreal_add_component`` **dependem do plugin de Python**, enquanto
``unreal_set_property`` e ``unreal_call_function`` funcionam com a RC API
pura. O código não finge o contrário: quando o transporte é ``rc``, as duas
primeiras falham com mensagem explícita.

**Validação manual pendente (importante).** O texto abaixo foi escrito
contra a API pública do módulo ``unreal`` (a mesma que o editor expõe) e
contra o padrão usado pelos projetos pesquisados na Fase -1. Ele **não foi
executado dentro de um Unreal real** neste ambiente — não há Unreal aqui.
Por isso:

- cada gerador devolve ``(code, metadata)`` com ``needs_validation=True``;
- o código gerado usa apenas APIs estáveis do módulo ``unreal``
  (``EditorAssetLibrary``, ``AssetTools``, ``BlueprintEditorLibrary``);
- os nomes exatos de métodos que variam entre versões estão isolados em
  ``_API_NOTES`` e o erro do editor é propagado sem ser engolido.

Quem for validar deve rodar o roteiro de ``TESTE_LOCAL.md``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

#: Notas de divergência entre versões, para o validador humano.
_API_NOTES: Mapping[str, str] = {
    "EditorAssetLibrary.save_asset": (
        "Disponível em UE 5.0+. Se faltar, use save_loaded_asset ou remova a "
        "chamada e salve pelo editor."
    ),
    "AssetTools.create_asset": (
        "Assinatura mudou de nome de parâmetro entre 4.x e 5.x "
        "(asset_class/assetClass). O código usa a posicional."
    ),
    "BlueprintEditorLibrary.add_component": (
        "Requer o blueprint recém-criado estar carregado (não apenas existir "
        "no disco). O script carrega antes por isso."
    ),
}

#: Nome do asset: letras, números, underscore. Sem espaço nem barra.
_SAFE_ASSET_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
#: Caminho de pacote Unreal: começa com '/' e usa só segmentos seguros.
_SAFE_PACKAGE_PATH = re.compile(r"^/(?:[A-Za-z0-9_]+)(?:/[A-Za-z0-9_]+)*$")
#: Nome de classe de componente: C++ ou Blueprint, sem caracteres estranhos.
_SAFE_CLASS_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class PythonScriptError(ValueError):
    """Entrada inválida para geração de script (mensagem acionável)."""


@dataclass(frozen=True)
class GeneratedScript:
    """Script pronto + o que o validador humano precisa saber."""

    code: str
    purpose: str
    #: `True` porque nada aqui foi executado contra um Unreal real.
    needs_validation: bool = True
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise PythonScriptError("script gerado está vazio")

    def summary(self) -> dict[str, Any]:
        return {
            "purpose": self.purpose,
            "needs_validation": self.needs_validation,
            "notes": list(self.notes),
            "code_preview": self.code.strip().splitlines()[0][:120] if self.code.strip() else "",
        }


def _check_asset_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise PythonScriptError("nome do asset é obrigatório")
    name = name.strip()
    if not _SAFE_ASSET_NAME.match(name):
        raise PythonScriptError(
            f"nome de asset inválido: {name!r}. Use letras, números e underscore, "
            "começando por letra ou underscore (até 64 caracteres)."
        )
    return name


def _check_package_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise PythonScriptError("caminho de pacote é obrigatório")
    path = path.strip().rstrip("/")
    if not _SAFE_PACKAGE_PATH.match(path):
        raise PythonScriptError(
            f"caminho de pacote inválido: {path!r}. Use a forma /Pasta/Subpasta "
            "com segmentos de letras, números e underscore."
        )
    return path


def _check_class_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise PythonScriptError("nome de classe é obrigatório")
    name = name.strip()
    if not _SAFE_CLASS_NAME.match(name):
        raise PythonScriptError(
            f"nome de classe inválido: {name!r}. Use o nome C++ ou o nome do "
            "Blueprint sem prefixo, p.ex. 'StaticMeshComponent' ou 'BP_Inventario'."
        )
    return name


def _python_literal(value: Any) -> str:
    """Literal Python seguro — nunca interpolação crua de string.

    Usar ``json.dumps`` para strings evita que uma propriedade com aspas ou
    barra invertida vire código. Números e booleanos passam direto.
    """
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise PythonScriptError(
        f"valor de tipo {type(value).__name__} não pode ser embutido com segurança; "
        "use escalar (texto/número/booleano)."
    )


_HEADER = '''"""Script gerado automaticamente pelo LUMEN (app/unreal_bridge).

Gerado para: {purpose}
NAO VALIDADO contra um Unreal real — ver TESTE_LOCAL.md.

Os caminhos abaixo representam o "primeiro alvo disponivel"; ajuste-os
para o projeto alvo antes de confiar no resultado.
"""
import unreal

'''

_FOOTER = '''
if __name__ == "__main__":
    main()
'''


def build_blueprint_creation_script(
    asset_name: str,
    package_path: str = "/Game/Blueprints",
    *,
    parent_class: str = "Actor",
    save: bool = True,
) -> GeneratedScript:
    """Script que cria um Blueprint vazio no Content Browser.

    Usa ``AssetTools.create_asset`` com ``blueprint_factory`` — o caminho
    programático padrão para criar um ``Blueprint`` sem abrir o editor de
    Blueprint.
    """
    name = _check_asset_name(asset_name)
    folder = _check_package_path(package_path)
    parent = _check_class_name(parent_class)

    code = _HEADER.format(purpose=f"criar Blueprint {name} em {folder} (pai: {parent})")
    code += f'''
BLUEPRINT_NAME = {_python_literal(name)}
PACKAGE_PATH = {_python_literal(folder)}
PARENT_CLASS = {_python_literal(parent)}


def main():
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory = unreal.BlueprintFactory()
    # `parent_class` e o que faz o Blueprint derivar de Actor (ou de outra
    # classe). E o equivalente a escolher o "Parent Class" na UI; sem ele
    # um Blueprint nasce como Object.
    try:
        parent_cls = unreal.load_class(None, PARENT_CLASS)
    except Exception:
        parent_cls = None
    if parent_cls is None and hasattr(unreal, PARENT_CLASS):
        parent_cls = getattr(unreal, PARENT_CLASS)
    if parent_cls is not None:
        factory.set_editor_property("parent_class", parent_cls)

    full_path = PACKAGE_PATH + "/" + BLUEPRINT_NAME
    asset = asset_tools.create_asset(BLUEPRINT_NAME, PACKAGE_PATH,
                                     unreal.Blueprint, factory)
    if asset is None:
        unreal.log_error("LUMEN: create_asset devolveu None para " + full_path)
        return
    unreal.log("LUMEN: blueprint criado em " + full_path)
    if {save!r}:
        try:
            unreal.EditorAssetLibrary.save_asset(full_path)
            unreal.log("LUMEN: asset salvo")
        except Exception as exc:
            unreal.log_warning("LUMEN: falha ao salvar o asset: " + str(exc))

'''
    code += _FOOTER
    return GeneratedScript(
        code=code,
        purpose=f"criar Blueprint '{name}' em '{folder}'",
        notes=(
            "Requer o Python Editor Script Plugin habilitado E "
            "bEnableRemotePythonExecution=True em Config/DefaultRemoteControl.ini.",
            _API_NOTES["AssetTools.create_asset"],
            "Se o asset já existir, o editor devolve aviso e o script NÃO sobrescreve.",
        ),
    )


def build_add_component_script(
    blueprint_path: str,
    component_class: str,
    component_name: str = "",
    *,
    properties: Mapping[str, Any] | None = None,
    save: bool = True,
) -> GeneratedScript:
    """Script que adiciona um componente a um Blueprint existente.

    ``blueprint_path`` é o caminho do asset
    (``/Game/Blueprints/BP_Ator.BP_Ator``).
    """
    if not isinstance(blueprint_path, str) or not blueprint_path.strip():
        raise PythonScriptError("blueprint_path é obrigatório")
    path = blueprint_path.strip()
    # Um caminho de asset tem a forma /Pasta/Nome.Nome — validamos as duas partes.
    if "." in path.rsplit("/", 1)[-1]:
        package, _, object_name = path.rpartition(".")
        _check_package_path(package)
        _check_asset_name(object_name)
    else:
        package = path
        object_name = path.rsplit("/", 1)[-1]
        _check_package_path(package)
        _check_asset_name(object_name)

    cls = _check_class_name(component_class)
    comp_name = _check_asset_name(component_name) if component_name else ""

    props = dict(properties or {})
    for key in props:
        if not isinstance(key, str) or not _SAFE_CLASS_NAME.match(key):
            raise PythonScriptError(f"nome de propriedade inválido: {key!r}")

    literal_props = "{" + ", ".join(
        f"{_python_literal(k)}: {_python_literal(v)}" for k, v in props.items()
    ) + "}"

    code = _HEADER.format(
        purpose=f"adicionar componente {cls} a {path}"
    )
    code += f'''
BLUEPRINT_PATH = {_python_literal(path)}
COMPONENT_CLASS = {_python_literal(cls)}
COMPONENT_NAME = {_python_literal(comp_name)}
PROPERTIES = {literal_props}


def main():
    if not unreal.EditorAssetLibrary.does_asset_exist(BLUEPRINT_PATH):
        unreal.log_error("LUMEN: blueprint nao encontrado: " + BLUEPRINT_PATH)
        return
    bp = unreal.EditorAssetLibrary.load_asset(BLUEPRINT_PATH)
    if bp is None:
        unreal.log_error("LUMEN: falha ao carregar " + BLUEPRINT_PATH)
        return

    # BlueprintEditorLibrary opera sobre o Blueprint ABERTO no editor; por
    # isso carregamos o asset antes. E preciso abrir o editor de Blueprint
    # para esverdaderamente persistir os nos de componente — comportamento
    # que PRECISA de validacao manual.
    try:
        unreal.BlueprintEditorLibrary.open_blueprint(bp)
    except Exception as exc:
        unreal.log_warning("LUMEN: nao foi possivel abrir o blueprint: " + str(exc))

    try:
        comp = unreal.BlueprintEditorLibrary.add_component(bp, COMPONENT_CLASS,
                                                           COMPONENT_NAME or None)
    except TypeError:
        # Assinatura alternativa (sem nome) em algumas versoes.
        comp = unreal.BlueprintEditorLibrary.add_component(bp, COMPONENT_CLASS)
    if comp is None:
        unreal.log_error("LUMEN: add_component devolveu None")
        return

    for prop_name, value in PROPERTIES.items():
        try:
            comp.set_editor_property(prop_name, value)
        except Exception as exc:
            unreal.log_warning("LUMEN: falha ao definir " + prop_name + ": " + str(exc))

    unreal.log("LUMEN: componente adicionado")
    if {save!r}:
        try:
            unreal.BlueprintEditorLibrary.compile_blueprint(bp)
            unreal.EditorAssetLibrary.save_asset(BLUEPRINT_PATH)
            unreal.log("LUMEN: blueprint compilado e salvo")
        except Exception as exc:
            unreal.log_warning("LUMEN: falha ao compilar/salvar: " + str(exc))

'''
    code += _FOOTER
    return GeneratedScript(
        code=code,
        purpose=f"adicionar componente '{cls}' a '{path}'",
        notes=(
            "Requer Python Editor Script Plugin + bEnableRemotePythonExecution.",
            _API_NOTES["BlueprintEditorLibrary.add_component"],
            "Adicionar componente a um Blueprint é a operação MENOS previsível "
            "da ponte: a API de edição de Blueprint mudou bastante entre 5.0 e "
            "5.5. Valide no seu engine antes de confiar.",
        ),
    )


def build_compile_script(blueprint_path: str) -> GeneratedScript:
    """Script que compila um Blueprint e devolve erros de compilação."""
    if not isinstance(blueprint_path, str) or not blueprint_path.strip():
        raise PythonScriptError("blueprint_path é obrigatório")
    path = blueprint_path.strip()
    code = _HEADER.format(purpose=f"compilar {path}")
    code += f'''
BLUEPRINT_PATH = {_python_literal(path)}


def main():
    bp = unreal.EditorAssetLibrary.load_asset(BLUEPRINT_PATH)
    if bp is None:
        unreal.log_error("LUMEN: nao encontrado: " + BLUEPRINT_PATH)
        return
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    errors = []
    try:
        errors = unreal.BlueprintEditorLibrary.get_blueprint_compile_errors(bp) or []
    except AttributeError:
        unreal.log_warning("LUMEN: get_blueprint_compile_errors indisponivel nesta versao")
    if errors:
        unreal.log_error("LUMEN: erros de compilacao: " + str(errors))
    else:
        unreal.log("LUMEN: compilado sem erros reportados")

'''
    code += _FOOTER
    return GeneratedScript(
        code=code,
        purpose=f"compilar '{path}'",
        notes=(_API_NOTES["EditorAssetLibrary.save_asset"],),
    )


def build_save_script(package_paths: list[str] | None = None) -> GeneratedScript:
    """Script que salva o projeto (ou pastas específicas) no disco."""
    paths = []
    for path in package_paths or []:
        paths.append(_check_package_path(path))
    literal_paths = "[" + ", ".join(_python_literal(p) for p in paths) + "]"
    code = _HEADER.format(purpose="salvar assets do projeto")
    code += f'''
PACKAGE_PATHS = {literal_paths}


def main():
    if PACKAGE_PATHS:
        for folder in PACKAGE_PATHS:
            saved = unreal.EditorAssetLibrary.save_directory(folder, False, True)
            unreal.log("LUMEN: save_directory(" + folder + ") -> " + str(saved))
    else:
        unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
        unreal.log("LUMEN: pacotes sujos salvos")

'''
    code += _FOOTER
    return GeneratedScript(
        code=code,
        purpose="salvar assets",
        notes=(_API_NOTES["EditorAssetLibrary.save_asset"],),
    )


def parse_execution_result(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Interpreta a resposta do ``ExecutePythonCommandEx`` sem inventar sucesso.

    A forma exata da resposta vem do plugin de Python, não da referência
    HTTP — por isso o parser é tolerante: reconhece os campos que a
    comunidade e a documentação do plugin citam, e quando não reconhece
    nada devolve ``ok=False`` com o payload cru, em vez de dizer "deu
    certo" sem base.
    """
    if not isinstance(payload, Mapping):
        return {
            "ok": False,
            "output": "",
            "logs": [],
            "raw": payload,
            "unrecognized": True,
            "note": "Resposta do plugin de Python não é um objeto JSON.",
        }

    logs = payload.get("LogOutput") or payload.get("log_output") or []
    if isinstance(logs, Mapping):
        logs = [logs]
    log_entries = []
    for entry in logs if isinstance(logs, list) else []:
        if isinstance(entry, Mapping):
            log_entries.append({
                "type": str(entry.get("Type", entry.get("type", ""))),
                "text": str(entry.get("Output", entry.get("output", ""))),
            })
        else:
            log_entries.append({"type": "", "text": str(entry)})

    output = payload.get("CommandResult")
    if output is None:
        output = payload.get("command_result")
    normalized_output = "" if output is None else str(output)

    errors = [
        entry for entry in log_entries
        if entry["type"].lower() in {"error", "warning"}
    ]
    has_error_logs = any(e["type"].lower() == "error" for e in errors)

    recognized = any(
        key in payload
        for key in ("CommandResult", "command_result", "LogOutput", "log_output")
    )
    return {
        "ok": recognized and not has_error_logs,
        "output": normalized_output,
        "logs": log_entries,
        "errors": errors,
        "raw": dict(payload),
        "unrecognized": not recognized,
    }


__all__ = [
    "GeneratedScript",
    "PythonScriptError",
    "build_add_component_script",
    "build_blueprint_creation_script",
    "build_compile_script",
    "build_save_script",
    "parse_execution_result",
]
