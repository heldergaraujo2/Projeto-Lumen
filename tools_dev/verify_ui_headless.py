"""Verificação headless da UI da Lumen (sandbox sem display).

Substitui o toolkit Tk por fakes (``tests/fake_tk.py``) e exercita o fluxo
real com a composição real de ``main.build_app``:

  conversa (worker thread + streaming + memória)  ·  botão ⚙ Configurações
  · diálogo de IA (provider/modelo/chave, 👁, testar conexão, salvar)
  · aplicação imediata do novo provider no Agent, sem reiniciar
  · provedores: mock, openai e gemini (clients fake, sem rede).

Tk real não existe neste sandbox; no Windows (alvo) ele acompanha o Python.
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

LUMEN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LUMEN_ROOT))
sys.path.insert(0, str(LUMEN_ROOT / "tests"))

import app.ui.main_window as main_window  # noqa: E402
import app.ui.settings_dialog as settings_dialog_module  # noqa: E402
import app.ui.tools_dialog as tools_dialog_module  # noqa: E402
from tests.fake_tk import FakeMessagebox, FakeRoot, FakeTtkModule, FakeTkModule  # noqa: E402
from tests.test_gemini_provider import (  # noqa: E402
    FakeGeminiClient,
    gemini_response,
    stream_chunk,
)

CHAVE = "sk-HARNESS-NAO-REAL-1"
CHAVE_GEMINI = "sk-HARNESS-GEMINI-NAO-REAL-2"


class FakeClient:
    """Client OpenAI falso (sem rede) para o provedor real simulado."""

    def __init__(self):
        self.calls: list[dict] = []

    def _create(self, **kwargs):
        self.calls.append(kwargs)

        class _Resp:
            choices = [SimpleNamespace(message=SimpleNamespace(content="pong"),
                                       finish_reason="stop")]
            model = "gpt-teste"
            usage = None

        return _Resp()

    @property
    def chat(self):
        return SimpleNamespace(completions=SimpleNamespace(create=self._create))


def wait_threads(name: str, deadline_s: float = 5.0) -> None:
    end = time.time() + deadline_s
    while time.time() < end:
        if not [t for t in threading.enumerate() if t.name == name]:
            return
        time.sleep(0.01)


def main() -> int:
    main_window.tk = FakeTkModule()
    settings_dialog_module.tk = FakeTkModule()
    settings_dialog_module.ttk = FakeTtkModule()
    settings_dialog_module.messagebox = FakeMessagebox(answer=True)
    tools_dialog_module.tk = FakeTkModule()
    tools_dialog_module.messagebox = FakeMessagebox(answer=True)

    import main as lumen_main
    from app.ai.gemini_provider import DEFAULT_MODEL, GeminiProvider
    from app.ai.openai_provider import OpenAIProvider
    from app.config.secrets import API_KEY_NAME
    from app.config.settings import Settings

    checks = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Settings(provider="mock", data_dir=Path(tmp))

        # ------------------------------------------------- conversa (0.2)
        agent, service = lumen_main.build_app(base)
        root = FakeRoot()
        window = main_window.LumenWindow(root, agent, config_service=service)

        checks.append(("título da janela", root.window_title == "Lumen"))
        checks.append(("botão ⚙ Configurações presente",
                       "Configurações" in window.settings_button.cget("text")))
        checks.append(("provedor exibido no cabeçalho", "mock" in window.subtitle_label.cget("text")))

        window.entry.insert(0, "Olá Lumen")
        window.send()
        end = time.time() + 5
        while time.time() < end and agent.memory.count < 2:
            time.sleep(0.01)
        window._poll_queue()
        conv = window.conversation.text
        checks.append(("mensagem exibida", "Você" in conv and "Olá Lumen" in conv))
        checks.append(("resposta exibida sem duplicação (boas-vindas + resposta)",
                       conv.count("Olá! Eu sou a Lumen") == 2))
        checks.append(("memória persistida", agent.memory.count == 2))

        # ------------------------------------------- diálogo de configurações
        window._open_settings()  # caminho real do botão ⚙ (abre e descarta)
        dialog = settings_dialog_module.SettingsDialog(root, service,
                                                       on_saved=window._refresh_provider_label)
        combobox_values = dialog.provider_combo.cget("values")
        checks.append(("combobox lista mock/openai/gemini",
                       all(p in combobox_values for p in ("mock", "openai", "gemini"))))
        checks.append(("diálogo abre com provider atual", dialog.provider_combo.get() == "mock"))
        checks.append(("campo de chave começa oculto (•)", dialog.key_entry.cget("show") == "•"))
        checks.append(("chave salva nunca é exibida", dialog.key_entry.get() == ""))

        dialog.toggle_key_visibility()
        visivel = dialog.key_entry.cget("show") == ""
        dialog.toggle_key_visibility()
        oculto = dialog.key_entry.cget("show") == "•"
        checks.append(("👁 mostra/oculta a chave", visivel and oculto))

        # teste de conexão em modo mock (offline)
        dialog.test_connection()
        wait_threads("lumen-test-connection")
        dialog._poll_queue()
        checks.append(("TESTAR CONEXÃO (mock, offline) → 🟢",
                       "🟢" in dialog.status_label.cget("text")
                       and "MockProvider" in dialog.status_label.cget("text")))

        # salvar openai + chave (client fake injetado no serviço)
        openai_client = FakeClient()
        service._client_factory = lambda key, timeout: openai_client
        dialog.provider_combo.set("openai")
        dialog.model_entry.insert(0, "gpt-teste")
        dialog.key_entry.insert(0, CHAVE)
        dialog.save()
        checks.append(("SALVAR troca o provider do Agent sem reiniciar",
                       isinstance(agent.provider, OpenAIProvider)))
        checks.append(("campo de chave limpo após salvar", dialog.key_entry.get() == ""))
        saved = json.loads((Path(tmp) / "settings.json").read_text(encoding="utf-8"))
        checks.append(("settings.json sem segredos",
                       saved.get("provider") == "openai" and CHAVE not in json.dumps(saved)))
        cofre = json.loads((Path(tmp) / ".credentials.json").read_text(encoding="utf-8"))
        checks.append(("chave apenas no cofre", cofre.get(API_KEY_NAME) == CHAVE))
        checks.append(("cabeçalho da janela atualizado", "openai" in window.subtitle_label.cget("text")))

        # teste de conexão com provider openai simulado
        dialog._poll_queue()  # limpa fila residual
        dialog.test_connection()
        wait_threads("lumen-test-connection")
        dialog._poll_queue()
        checks.append(("TESTAR CONEXÃO (openai simulado) → 🟢",
                       "Conexão estabelecida" in dialog.status_label.cget("text")))
        checks.append(("requisição mínima (max_tokens=1)",
                       openai_client.calls and openai_client.calls[-1].get("max_tokens") == 1))
        checks.append(("chave nunca vai ao modelo",
                       CHAVE not in json.dumps(openai_client.calls[-1], default=str)))

        # ------------------------------------------------- gemini (0.2-compl.)
        def _gemini_stream(kwargs):
            meta = SimpleNamespace(prompt_token_count=1, candidates_token_count=1,
                                   total_tokens=2)
            return [
                stream_chunk("pong do gemini", model=DEFAULT_MODEL),
                stream_chunk(finish="STOP", usage=meta, model=DEFAULT_MODEL),
            ]

        gemini_client = FakeGeminiClient(
            lambda kw: gemini_response("pong do gemini"), [], stream_script=_gemini_stream
        )
        service._client_factory = lambda key, timeout: gemini_client

        dialog._poll_queue()  # limpa fila residual
        dialog.provider_combo.set("gemini")
        dialog.model_entry.delete(0, "end")  # modelo vazio → padrão
        dialog.key_entry.insert(0, CHAVE_GEMINI)
        dialog.save()
        checks.append(("SALVAR gemini troca o provider (modelo padrão)",
                       isinstance(agent.provider, GeminiProvider)
                       and agent.provider.model_name == DEFAULT_MODEL))
        checks.append(("cabeçalho mostra gemini + modelo",
                       "gemini" in window.subtitle_label.cget("text")
                       and DEFAULT_MODEL in window.subtitle_label.cget("text")))
        cofre2 = json.loads((Path(tmp) / ".credentials.json").read_text(encoding="utf-8"))
        checks.append(("chave gemini guardada no mesmo cofre",
                       cofre2.get(API_KEY_NAME) == CHAVE_GEMINI))

        dialog._poll_queue()
        dialog.test_connection()
        wait_threads("lumen-test-connection")
        dialog._poll_queue()
        status = dialog.status_label.cget("text")
        gemini_call = gemini_client._calls[-1] if gemini_client._calls else {}
        checks.append(("TESTAR CONEXÃO (gemini simulado) → 🟢",
                       "🟢" in status and "Conexão estabelecida" in status))
        checks.append(("sonda gemini sem limite de tokens (thinking)",
                       "max_output_tokens" not in (gemini_call.get("config") or {})))
        checks.append(("chave gemini nunca vai ao modelo",
                       CHAVE_GEMINI not in json.dumps(gemini_call, default=str)))

        # conversa real com o provider gemini aplicado
        window._set_busy(False)
        window.entry.insert(0, "testando gemini")
        window.send()
        fim_gemini = time.time() + 5
        while time.time() < fim_gemini and "pong do gemini" not in window.conversation.text:
            time.sleep(0.01)
        window._poll_queue()
        checks.append(("conversa usa o provider gemini",
                       "pong do gemini" in window.conversation.text))

        # remover chave (confirmado) e voltar ao mock
        dialog._remove_key()
        checks.append(("remover chave do cofre",
                       service.current_config()["has_stored_key"] is False))
        dialog.provider_combo.set("mock")
        dialog.model_entry.delete(0, "end")
        dialog.save()
        checks.append(("voltar ao mock e conversar com o provider aplicado",
                       agent.provider.name == "mock"
                       and agent.send_message("oi novamente").strip()))

        # ------------------------------------ ferramentas e segurança (0.5.x)
        from app.planner.models import (  # noqa: E402
            Plan as ToolsPlan,
            PlanStatus as ToolsPlanStatus,
            PlannedTask as ToolsTask,
        )
        from app.tools.control import ToolsController  # noqa: E402

        workdir = Path(tmp) / "workspace_docs"
        workdir.mkdir()
        (workdir / "base.txt").write_text("olá", encoding="utf-8")
        tools_controller = ToolsController(
            agent.permissions,
            workspaces_file=Path(tmp) / "workspaces.json",
            audit_file=Path(tmp) / "audit" / "audit.jsonl",
        )
        checks.append(("botão 🛡 Ferramentas presente",
                       "Ferramentas" in window.tools_button.cget("text")))
        window._open_tools()  # caminho real do botão
        tools_ui = tools_dialog_module.ToolsDialog(root, tools_controller)
        checks.append(("🛡 abre sem workspaces e sem aprovação pendente",
                       tools_ui.ws_rows == [] and "Nenhuma operação aguardando"
                       in tools_ui.pending_label.cget("text")))
        checks.append(("permissões na tela: apenas CHAT por padrão",
                       "● concedida" in tools_ui.perm_rows["CHAT"]["status"].cget("text")
                       and "○ não concedida" in tools_ui.perm_rows["READ"]["status"].cget("text")))
        tools_ui._toggle_permission("READ")
        tools_ui._toggle_permission("WRITE")
        tools_ui.path_entry.insert(0, str(workdir))
        tools_ui._toggle_write()
        tools_ui._add_workspace()
        checks.append(("workspace autorizado aparece com modo (escrita)",
                       len(tools_ui.ws_rows) == 1
                       and tools_ui.ws_rows[0]["mode"] == "escrita"))

        tool_tasks = (
            ToolsTask(id="T1", description="ler base", order=1,
                      tool="read_file", parameters={"path": "base.txt"}),
            ToolsTask(id="T2", description="criar notas", order=2,
                      dependencies=("T1",), tool="create_file",
                      parameters={"path": "notas.txt",
                                  "content": "CONTEUDO-SEGREDO-H"}),
        )
        tools_controller.run_plan(ToolsPlan(
            id="PLN-H", objective="organizar documentos",
            status=ToolsPlanStatus.READY, tasks=tool_tasks,
        ))
        tools_ui.refresh()
        pending_text = tools_ui.pending_label.cget("text")
        checks.append(("aprovação pendente mostra o quê/onde/ferramenta/permissão",
                       all(fragment in pending_text for fragment in (
                           "AGUARDANDO APROVAÇÃO", "O que: criar notas",
                           "Ferramenta: create_file", "Operação: escrita",
                           "Permissão: WRITE", "Onde: notas.txt"))))
        checks.append(("operação destrutiva bloqueada até aprovação",
                       not (workdir / "notas.txt").exists()))
        tools_ui._refuse()
        checks.append(("recusa na UI NÃO executa a operação",
                       not (workdir / "notas.txt").exists()
                       and "NÃO foi executada" in tools_ui.status_label.cget("text")))
        tools_controller.run_plan(ToolsPlan(
            id="PLN-H2", objective="organizar documentos (2ª tentativa)",
            status=ToolsPlanStatus.READY, tasks=tool_tasks,
        ))
        tools_ui.refresh()
        tools_ui._approve()
        checks.append(("aprovação na UI executa a operação",
                       (workdir / "notas.txt").read_text(encoding="utf-8")
                       == "CONTEUDO-SEGREDO-H"))
        tools_ui._refresh_audit()
        checks.append(("auditoria lista operações com tarefa/plano",
                       "create_file" in tools_ui.audit_text.text
                       and "T2/PLN-H2" in tools_ui.audit_text.text))
        checks.append(("auditoria sem conteúdo de arquivos",
                       "CONTEUDO-SEGREDO-H" not in tools_ui.audit_text.text))
        tools_ui.ws_rows[0]["remove_button"].invoke()
        checks.append(("remover workspace pela UI",
                       tools_controller.list_workspaces() == []))

        # ---------------------------------------------- terminal (0.6)
        from app.planner.models import Plan as TermPlan  # noqa: E402
        from app.planner.models import PlanStatus as TermPlanStatus  # noqa: E402
        from app.planner.models import PlannedTask as TermTask  # noqa: E402

        tools_controller.add_workspace(str(workdir))
        checks.append(("startup da UI sem ferramenta de terminal",
                       "run_command" not in [t["name"] for t in
                                             tools_controller.build_registry()
                                             .list_tools()]))
        tools_controller.enable_terminal(["mkdir"])
        agent.permissions.grant("TERMINAL")  # concessão programática
        tools_controller.run_plan(TermPlan(
            id="PLN-H3", objective="criar pasta por comando",
            status=TermPlanStatus.READY,
            tasks=(TermTask(id="T1", description="criar pasta dados",
                            order=1, tool="run_command",
                            parameters={"command": "mkdir",
                                        "args": ["dados-h"], "cwd": "."}),),
        ))
        tools_ui.refresh()
        pending_text = tools_ui.pending_label.cget("text")
        checks.append(("card mostra comando/argumentos/diretório/timeout",
                       "Ferramenta: run_command" in pending_text
                       and "Comando: mkdir" in pending_text
                       and "Argumentos: dados-h" in pending_text
                       and "Diretório de trabalho:" in pending_text
                       and "Timeout: 10s" in pending_text
                       and "Permissão: TERMINAL" in pending_text))
        checks.append(("comando bloqueado até aprovação",
                       not (workdir / "dados-h").exists()))
        tools_ui._refuse()
        checks.append(("recusa de comando NÃO executa nada",
                       not (workdir / "dados-h").exists()))
        tools_controller.run_plan(TermPlan(
            id="PLN-H4", objective="criar pasta dados (2ª)",
            status=TermPlanStatus.READY,
            tasks=(TermTask(id="T1", description="criar pasta dados",
                            order=1, tool="run_command",
                            parameters={"command": "mkdir",
                                        "args": ["dados-h"], "cwd": "."}),),
        ))
        tools_ui.refresh()
        tools_ui._approve()
        checks.append(("aprovação de comando executa (dentro do workspace)",
                       (workdir / "dados-h").exists()))
        tools_controller.disable_terminal()

        # --------------------------------------- UI terminal (0.6.x)
        checks.append(("nenhum arquivo de allowlist criado pelo controller",
                       not (Path(tmp) / "terminal.json").exists()))
        agent.permissions.revoke("TERMINAL")  # estado limpo p/ fluxo 0.6.x
        checks.append(("TERMINAL não fica concedida sem ação explícita",
                       not agent.permissions.is_granted("TERMINAL")))
        agent.permissions.grant("TERMINAL")  # re-habilita p/ fluxo da UI
        tools_ui.refresh()
        checks.append(("seção TERMINAL mostra concessão e allowlist",
                       "TERMINAL concedida" in tools_ui.terminal_status_label
                       .cget("text")
                       and "allowlist: 0 comando" in tools_ui.terminal_status_label
                       .cget("text")))
        tools_ui.cmd_entry.insert(0, "printf")
        tools_ui.cmd_approval_toggle.invoke()  # executa direto
        tools_ui.add_cmd_button.invoke()
        checks.append(("comando cadastrado pela UI entra na allowlist",
                       [c["name"] for c in tools_controller
                        .list_allowed_commands()] == ["printf"]
                       and tools_ui.term_rows[0]["name"] == "printf"
                       and tools_controller.terminal_status()["allowed_count"] == 1))
        tools_ui.cmd_entry.insert(0, "powershell")
        tools_ui.add_cmd_button.invoke()
        checks.append(("UI rejeita comando da denylist permanente",
                       "🔴" in tools_ui.status_label.cget("text")
                       and [c["name"] for c in tools_controller
                            .list_allowed_commands()] == ["printf"]))
        tools_ui.term_rows[0]["remove_button"].invoke()
        checks.append(("remoção pela UI esvazia a allowlist",
                       tools_controller.list_allowed_commands() == []
                       and tools_ui.term_rows == []))
        tools_ui.terminal_toggle.invoke()  # revoga
        checks.append(("revogação pela UI bloqueia TERMINAL",
                       not agent.permissions.is_granted("TERMINAL")))
        tools_ui.terminal_toggle.invoke()  # concede de volta (explícito)
        checks.append(("concessão explícita pela UI",
                       agent.permissions.is_granted("TERMINAL")))
        ops = [r["operation"] for r in tools_controller.audit_records()]
        checks.append(("ações administrativas de terminal auditadas",
                       all(op in ops for op in ("terminal_grant",
                                                "terminal_revoke",
                                                "allowlist_add",
                                                "allowlist_remove"))))

        active = [t for t in threading.enumerate() if t.name == "lumen-agent-worker"]
        checks.append(("nenhuma worker presa", all(not t.is_alive() for t in active)))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if failed:
        print(f"\n{len(failed)} verificação(ões) falharam.")
        return 1
    print(f"\nTodas as {len(checks)} verificações de UI passaram (headless).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
