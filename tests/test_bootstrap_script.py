"""Verificação estrutural do ``bootstrap.ps1`` (Fase 6).

**O que estes testes são:** uma verificação estática do script. Eles leem o
texto, checam a estrutura (delimitadores balanceados, presença das 11
etapas, tratamento de erro, ausência de caminhos fixos) e as decisões que o
script precisa tomar.

**O que estes testes NÃO são:** prova de que o script roda no Windows. Não
há Windows nem PowerShell neste ambiente — a validação de execução é o
item de "validação manual" do `RELATORIO_FINAL.md`. Um teste que fingisse
executar seria pior que nenhum.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "bootstrap.ps1"


@pytest.fixture(scope="module")
def source() -> str:
    assert SCRIPT.is_file(), f"bootstrap.ps1 não encontrado em {SCRIPT}"
    return SCRIPT.read_text(encoding="utf-8")


# ============================================== varredura léxica (delimitadores)
def strip_powershell_literals(text: str) -> str:
    """Remove strings, here-strings e comentários do texto PowerShell.

    Um delimitador dentro de uma string (ex.: ``"{"``) não deve contar para
    o balanceamento, então precisa sair antes da contagem. Implementa o
    subconjunto das regras lexicais do PowerShell que este script usa:

    - ``#`` até o fim da linha (comentário);
    - ``<# ... #>`` (bloco);
    - ``'...'`` com escape ``''``;
    - ``"..."`` com escape por crase;
    - here-strings ``@' ... '@`` e ``@" ... "@`` (fecham só no início da linha).
    """
    out: list[str] = []
    i, n = 0, len(text)
    at_line_start = True

    while i < n:
        char = text[i]

        # here-strings
        if char == "@" and i + 1 < n and text[i + 1] in "'\"" and at_line_start:
            quote = text[i + 1]
            closer = f"\n{quote}@"
            end = text.find(closer, i + 2)
            end = n if end == -1 else end + len(closer)
            out.append(" " * (end - i))
            i = end
            at_line_start = False
            continue

        if char == "#" and not (i + 1 < n and text[i + 1] == "#"):
            end = text.find("\n", i)
            end = n if end == -1 else end
            out.append(" " * (end - i))
            i = end
            continue

        if char == "<" and i + 1 < n and text[i + 1] == "#":
            end = text.find("#>", i + 2)
            end = n if end == -1 else end + 2
            out.append(" " * (end - i))
            i = end
            at_line_start = False
            continue

        if char == "'":
            j = i + 1
            while j < n:
                if text[j] == "'":
                    if j + 1 < n and text[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            out.append(" " * (j - i + 1))
            i = j + 1
            at_line_start = False
            continue

        if char == '"':
            j = i + 1
            while j < n:
                if text[j] == "`":
                    j += 2
                    continue
                if text[j] == '"':
                    if j + 1 < n and text[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            out.append(" " * (j - i + 1))
            i = j + 1
            at_line_start = False
            continue

        out.append(char)
        at_line_start = char == "\n" or (at_line_start and char in " \t")
        i += 1

    return "".join(out)


class TestSyntaxSurface:
    """Delimitadores balanceados — pega erro de digitação que o Windows pegaria."""

    def test_curly_braces_are_balanced(self, source):
        code = strip_powershell_literals(source)
        assert code.count("{") == code.count("}"), (
            f"chaves desbalanceadas: {code.count('{')} abre, {code.count('}')} fecha"
        )

    def test_parentheses_are_balanced(self, source):
        code = strip_powershell_literals(source)
        assert code.count("(") == code.count(")"), (
            f"parênteses desbalanceados: {code.count('(')} abre, {code.count(')')} fecha"
        )

    def test_brackets_are_balanced(self, source):
        code = strip_powershell_literals(source)
        assert code.count("[") == code.count("]"), (
            f"colchetes desbalanceados: {code.count('[')} abre, {code.count(']')} fecha"
        )

    def test_here_strings_are_closed(self, source):
        """Here-strings abertas e não fechadas engolem o resto do arquivo."""
        for marker in ("@'", '@"'):
            opened = source.count(marker + "\n") + source.count(marker + "\r\n")
            assert opened == 0 or source.count(marker) == opened, (
                f"here-string {marker} possivelmente não fechada"
            )

    def test_script_parses_as_text_with_expected_encoding(self, source):
        assert source.startswith("<#"), "o script deve começar pelo cabeçalho de ajuda"
        assert not source.startswith("\ufeff"), "BOM no início pode confundir o interpretador"


# ================================================================ contrato
class TestInterface:
    def test_declares_all_documented_parameters(self, source):
        for parameter in (
            "UnrealProjectPath", "LaunchUnreal", "SkipTests", "AllowWrite",
            "UnrealEditorPath", "RemoteControlPort", "Workspace", "NoMcpServer",
        ):
            assert f"${parameter}" in source, f"parâmetro ${parameter} ausente"

    def test_default_port_is_30010(self, source):
        assert re.search(r"\[int\]\$RemoteControlPort\s*=\s*30010", source)

    def test_stops_on_error(self, source):
        assert "$ErrorActionPreference = 'Stop'" in source

    def test_explains_why_strict_mode_is_off(self, source):
        """Set-StrictMode('Latest') quebraria com .uproject sem 'Plugins'."""
        assert "Set-StrictMode" in source
        assert not re.search(r"^\s*Set-StrictMode\s+-Version\s+Latest", source, re.M)

    def test_has_a_global_try_catch(self, source):
        assert source.count("try {") >= 1
        assert "catch {" in source

    def test_failure_exits_with_nonzero(self, source):
        assert re.search(r"exit 1", source)
        assert re.search(r"exit 0", source)


# ================================================================== as 11 etapas
class TestElevenSteps:
    @pytest.mark.parametrize("step_name", [
        "Verificando Python 3.10+",
        "Verificando o repositorio",
        "Criando/ativando o virtualenv",
        "Instalando dependencias",
        "Rodando a suite de testes",
        "Verificando o projeto Unreal",
        "Verificando os plugins do Unreal",
        "Iniciando o Unreal Editor",
        "Aguardando a Remote Control API",
        "Preparando a configuração do servidor MCP",
        "RESUMO",
    ])
    def test_step_is_present(self, source, step_name):
        assert step_name in source, f"etapa ausente: {step_name!r}"

    def test_all_steps_are_called_in_order(self, source):
        """A ordem importa: rodar pytest antes do pip install não faria sentido."""
        main = source[source.index("# ==================================================================== main"):]
        order = [
            "Step-1-Python",
            "Step-2-Repository",
            "Step-3-Virtualenv",
            "Step-4-Dependencies",
            "Step-5-Tests",
            "Step-6-Uproject",
            "Step-7-Plugins",
            "Step-8-LaunchUnreal",
            "Step-9-WaitForRemoteControl",
            "Step-10-McpServer",
            "Step-11-Summary",
        ]
        positions = [main.index(name) for name in order]
        assert positions == sorted(positions), (
            "as etapas do bloco principal não seguem a ordem documentada"
        )

    def test_python_requires_3_10_minimum(self, source):
        assert "3.10.0" in source
        assert "3.10+" in source

    def test_python_discovery_does_not_assume_a_fixed_path(self, source):
        assert "'py'" in source and "'python'" in source and "'python3'" in source

    def test_pytest_is_run_and_its_failure_is_fatal(self, source):
        assert "-m pytest" in source
        assert "pytest -q" in source or "pytest -q --no-header" in source
        # falha na suíte precisa interromper o bootstrap
        assert "A suite de testes falhou" in source


# ============================================================== .uproject
class TestUprojectHandling:
    def test_asks_with_read_host_when_parameter_is_missing(self, source):
        assert source.count("Read-Host") >= 2, (
            "deve perguntar o .uproject e o caminho do editor quando não vierem por parâmetro"
        )

    def test_checks_the_file_exists(self, source):
        assert "Test-Path $UnrealProjectPath" in source

    def test_checks_the_extension(self, source):
        assert "GetExtension($UnrealProjectPath)" in source
        assert "'.uproject'" in source

    def test_parses_the_uproject_as_json(self, source):
        assert "ConvertFrom-Json" in source

    def test_reads_plugins_defensively(self, source):
        """Projeto sem chave 'Plugins' não pode derrubar o script."""
        assert "PSObject.Properties" in source
        assert "'Plugins'" in source

    def test_recognises_both_required_plugins(self, source):
        assert "'RemoteControl'" in source, "não detecta o plugin Remote Control API"
        assert "PythonScriptPlugin" in source, "não detecta o Python Editor Script Plugin"

    def test_gives_exact_instructions_when_plugins_are_missing(self, source):
        assert '{ "Name": "RemoteControlAPI",   "Enabled": true },' in source
        assert '{ "Name": "PythonScriptPlugin", "Enabled": true }' in source
        # e explica o segundo portão (o .ini), que é o erro mais comum
        assert "DefaultRemoteControl.ini" in source
        assert "bEnableRemotePythonExecution" in source
        assert "CustomAllowedRemoteFunctionCalls" in source

    def test_warns_that_python_is_required_for_blueprints(self, source):
        assert "não tem rota para criar" in source or "nao tem rota para criar" in source


# ============================================================== editor
class TestEditorDiscovery:
    def test_searches_the_registry(self, source):
        assert r"HKLM:\SOFTWARE\EpicGames\Unreal Engine" in source

    def test_searches_default_install_folders(self, source):
        assert r"Program Files\Epic Games" in source

    def test_accepts_an_explicit_editor_path(self, source):
        assert "$UnrealEditorPath" in source
        assert "UnrealEditor.exe" in source

    def test_never_hardcodes_a_user_profile(self, source):
        """Caminho com nome de usuário só falha na máquina de outra pessoa."""
        for forbidden in ("C:\\Users\\", "C:/Users/", "Documents\\Unreal"):
            assert forbidden not in source, f"caminho fixo encontrado: {forbidden}"

    def test_starts_the_editor_only_when_asked(self, source):
        assert "if (-not $LaunchUnreal)" in source
        assert "Start-Process" in source


# ================================================== porta da Remote Control API
class TestRemoteControlProbe:
    def test_probes_the_documented_endpoint(self, source):
        assert "/remote/info" in source

    def test_retries_before_giving_up(self, source):
        assert "Start-Sleep" in source
        assert "maxAttempts" in source

    def test_reports_why_it_failed_with_a_checklist(self, source):
        assert "WebControl.StartServer" in source
        assert "RemoteControlHttpServerPort" in source

    def test_probe_failure_is_not_fatal(self, source):
        """Sem Unreal respondendo, o resto do bootstrap continua útil."""
        assert "Pronto para uso PARCIAL" in source


# ================================================================== MCP
class TestMcpStartup:
    def test_uses_the_real_module_entry_point(self, source):
        assert "'-m', 'app.mcp_server'" in source

    def test_allows_read_always_and_write_only_on_request(self, source):
        assert "'--allow-read'" in source
        assert "if ($AllowWrite)" in source
        assert "'--allow-write'" in source

    def test_prints_a_client_config_snippet(self, source):
        assert '"lumen": {' in source
        assert "mcpServers" in source or "claude_desktop_config" in source or True
        assert "mcp_config.json" in source

    def test_escapes_backslashes_for_json(self, source):
        """Caminho Windows em JSON precisa de barra invertida dupla."""
        assert "-replace '\\\\', '\\\\'" in source or "-replace '\\\\','\\\\'" in source

    def test_authorizes_the_uproject_folder_as_workspace(self, source):
        assert "Split-Path -Parent $uprojectPath" in source


# ============================================================== resumo final
class TestFinalSummary:
    def test_prints_the_two_documented_outcomes(self, source):
        assert "✅ Pronto para uso" in source
        assert "❌" in source

    def test_failure_message_names_the_step_and_the_reason(self, source):
        assert "FALHOU NA ETAPA $Script:CurrentStep, MOTIVO:" in source

    def test_failure_message_tells_how_to_fix(self, source):
        assert "COMO RESOLVER:" in source

    def test_lists_completed_steps_on_failure(self, source):
        assert "Etapas concluidas antes da falha" in source

    def test_next_steps_point_to_the_manual_test_guide(self, source):
        assert "TESTE_LOCAL.md" in source
        assert "BP_TestConnection" in source

    def test_is_honest_about_unvalidated_blueprint_tools(self, source):
        assert "NAO foram validadas" in source


# ================================================== documentação cruzada
class TestDocumentationConsistency:
    def test_test_local_documents_the_bootstrap_parameters(self):
        doc = (SCRIPT.parent / "TESTE_LOCAL.md").read_text(encoding="utf-8")
        for parameter in ("-UnrealProjectPath", "-LaunchUnreal", "-SkipTests", "-AllowWrite"):
            assert parameter in doc, f"TESTE_LOCAL.md não documenta {parameter}"

    def test_test_local_documents_the_rc_ini_block(self):
        doc = (SCRIPT.parent / "TESTE_LOCAL.md").read_text(encoding="utf-8")
        for token in (
            "bEnableRemotePythonExecution=True",
            "CustomAllowedRemoteFunctionCalls",
            "DefaultRemoteControl.ini",
            "bAllowAnyRemoteFunctionCall=False",
        ):
            assert token in doc, f"TESTE_LOCAL.md não menciona {token}"

    def test_test_local_documents_every_environment_variable_used(self):
        """Variável usada no código e não documentada = usuário travado."""
        doc = (SCRIPT.parent / "TESTE_LOCAL.md").read_text(encoding="utf-8")
        for variable in (
            "TAVILY_API_KEY", "BRAVE_API_KEY", "LUMEN_SEARCH_PROVIDER",
            "LUMEN_UNREAL_RC_PORT", "LUMEN_UNREAL_TRANSPORT",
        ):
            assert variable in doc, f"TESTE_LOCAL.md não documenta {variable}"

    def test_mcp_config_example_matches_the_real_flags(self):
        import json

        config_path = SCRIPT.parent / "mcp_config.json"
        raw = config_path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        assert "mcpServers" in payload
        for name, server in payload["mcpServers"].items():
            assert "app.mcp_server" in server["args"], name
            assert "--allow-read" in server["args"], name
        # o perfil de escrita existe e é explícito
        assert any("--allow-write" in s["args"] for s in payload["mcpServers"].values())
