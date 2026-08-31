"""Ponto de entrada da Lumen.

Execução (na raiz do projeto)::

    python main.py

Monta as camadas (provedor → memória → tarefas → permissões → agent +
serviço de configuração), configura o logging e abre a interface
Tkinter. A configuração de IA vigente combina: configuração gráfica
salva (``data/settings.json`` + cofre) > variáveis de ambiente > ``.env``
> padrões — ver ``app/config/user_config.py``.
"""
from __future__ import annotations

import logging
import sys

from app import __version__
from app.ai.provider import create_provider
from app.config.config_service import ConfigService
from app.config.secrets import create_secret_store
from app.config.settings import Settings, setup_logging
from app.config.user_config import UserConfigError, UserConfigStore, apply_user_overrides
from app.core.agent import Agent
from app.memory.store import MemoryStore
from app.memory.system import MemorySystem
from app.security.permissions import PermissionManager
from app.tasks.manager import TaskManager
from app.tools.control import ToolsController

LOGGER = logging.getLogger("lumen")


def build_app(settings: Settings) -> tuple[Agent, ConfigService]:
    """Composition root: monta Agent + ConfigService.

    A configuração gráfica salva pelo usuário (se existir) tem prioridade
    sobre ``.env``/ambiente; a API Key vem do cofre (fallback ``.env``).
    """
    user_store = UserConfigStore(settings.data_dir / UserConfigStore.FILENAME)
    try:
        overrides = user_store.load()
    except UserConfigError as exc:
        LOGGER.error("Configuração do usuário ignorada: %s", exc)
        overrides = {}

    secrets = create_secret_store(settings.data_dir)
    effective = apply_user_overrides(settings, overrides, secrets)

    provider = create_provider(effective)
    memory = MemoryStore(effective.memory_file)
    task_manager = TaskManager(effective.tasks_file)
    permissions = PermissionManager()  # apenas CHAT nesta fase
    # Memória estruturada 0.3: montada sem efeitos colaterais (arquivos
    # de domínio só nascem no primeiro save) e usada como contexto de
    # LEITURA pelo Planner (request_plan) — o fluxo de conversa não muda.
    memory_system = MemorySystem(
        settings.data_dir, max_context_records=effective.max_memory_records
    )
    agent = Agent(
        provider=provider,
        memory=memory,
        permissions=permissions,
        task_manager=task_manager,
        context_window=effective.max_context_messages,
        memory_system=memory_system,
    )
    service = ConfigService(
        base_settings=settings,
        user_store=user_store,
        secrets=secrets,
        agent=agent,
    )
    return agent, service


def build_agent(settings: Settings) -> Agent:
    """Monta apenas o Agent (mantido para compatibilidade com testes)."""
    agent, _service = build_app(settings)
    return agent


def main() -> int:
    """Inicializa a aplicação; devolve o código de saída do processo."""
    try:
        settings = Settings.load()
        setup_logging(settings)
    except Exception:
        LOGGER.exception("Falha ao carregar configurações/logging.")
        print("Erro de configuração — veja o terminal ou data/logs/lumen.log.", file=sys.stderr)
        return 1

    LOGGER.info("=" * 60)
    LOGGER.info(
        "Iniciando a Lumen v%s (provedor=%s, nível de log=%s).",
        __version__,
        settings.provider,
        settings.log_level,
    )

    try:
        agent, config_service = build_app(settings)
    except Exception as exc:
        LOGGER.error("Falha ao inicializar os componentes da Lumen: %s", exc)
        LOGGER.exception("Detalhes técnicos:")
        return 1

    current = config_service.current_config()
    LOGGER.info(
        "Componentes inicializados: provedor=%s (modelo=%s, chave=%s), memória=%s, tarefas=%s.",
        agent.provider.name,
        agent.provider.model_name or "-",
        current["key_source"],
        settings.memory_file,
        settings.tasks_file,
    )

    try:
        root = tk_root()
    except Exception:
        # Ex.: ambientes Linux/CI sem display. No Windows (alvo) nunca ocorre.
        LOGGER.exception("Não foi possível abrir a janela Tk (display disponível?).")
        return 1

    try:
        from app.ui.main_window import LumenWindow

        # 0.5.x: camada de controle de ferramentas (workspaces/permissões/
        # checkpoints/auditoria) — construída sem efeitos colaterais (nenhum
        # arquivo nasce, nenhuma permissão é concedida no startup).
        tools_controller = ToolsController(
            agent.permissions or PermissionManager(),
            workspaces_file=settings.data_dir / "workspaces.json",
            audit_file=settings.data_dir / "audit" / "audit.jsonl",
            # 0.6.x: allowlist persistida (data/terminal.json). Apenas
            # LIDA no startup — sem arquivo, terminal segue desabilitado;
            # a permissão TERMINAL nunca é restaurada (explícita/sessão).
            terminal_file=settings.data_dir / "terminal.json",
        )
        # 0.6.3: liga o chat à fachada de ferramentas (tool calling via
        # Planner com allowlist). Sem concessões: a autoridade segue no
        # controller (permissões/workspaces/checkpoints/auditoria).
        agent.set_tools_controller(tools_controller)
        window = LumenWindow(
            root, agent,
            config_service=config_service,
            tools_controller=tools_controller,
        )
        window.run()
    finally:
        LOGGER.info("Lumen encerrada.")
    return 0


def tk_root():
    """Cria a janela raiz Tk (separado para clareza/testes)."""
    import tkinter as tk

    return tk.Tk()


if __name__ == "__main__":
    sys.exit(main())
