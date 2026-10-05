"""Ponto de entrada da Lumen com runtime universal opcional."""
from __future__ import annotations

import argparse
import logging
import sys

from app import __version__
from app.ai.provider import create_provider
from app.config.config_service import ConfigService
from app.config.secrets import create_secret_store
from app.config.settings import PROJECT_ROOT, Settings, setup_logging
from app.config.user_config import UserConfigError, UserConfigStore, apply_user_overrides
from app.core.agent import Agent
from app.memory.store import MemoryStore
from app.memory.system import MemorySystem
from app.security.permissions import PermissionManager
from app.tasks.manager import TaskManager
from app.tools.control import ToolsController
from app.computer.windows_native import WindowsNativeIntelligence
from app.computer_control.service import ComputerControlService
from app.computer_control.windows_driver import WindowsComputerControlDriver
from app.unreal.integration import UnrealIntegration
from app.unreal.mcp import UnrealMCPClient
from app.runtime.plugins import PluginManager
from app.evolution.autonomous_mission import AutonomousMissionSupervisor

LOGGER = logging.getLogger("lumen")


def build_app(settings: Settings) -> tuple[Agent, ConfigService]:
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
    permissions = PermissionManager()
    memory_system = MemorySystem(settings.data_dir, max_context_records=effective.max_memory_records)
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
    agent, _service = build_app(settings)
    return agent


def main() -> int:
    parser = argparse.ArgumentParser(description="Inicia a interface gráfica da Lumen.")
    parser.add_argument("--no-autonomous-mission-supervisor", action="store_true")
    args = parser.parse_args()
    try:
        settings = Settings.load()
        setup_logging(settings)
    except Exception:
        LOGGER.exception("Falha ao carregar configurações/logging.")
        print("Erro de configuração — veja o terminal ou data/logs/lumen.log.", file=sys.stderr)
        return 1

    try:
        agent, config_service = build_app(settings)
    except Exception as exc:
        LOGGER.error("Falha ao inicializar os componentes da Lumen: %s", exc)
        LOGGER.exception("Detalhes técnicos:")
        return 1

    plugin_manager = PluginManager()
    plugin_reports = plugin_manager.discover()

    try:
        root = tk_root()
    except Exception:
        LOGGER.exception("Não foi possível abrir a janela Tk.")
        return 1

    try:
        from app.ui.main_window import LumenWindow

        def mission_supervisor_factory():
            return AutonomousMissionSupervisor(
                repo=PROJECT_ROOT,
                data_dir=settings.data_dir,
                model=agent.provider.model_name or settings.model or "qwen2.5-coder:7b-instruct-q8_0",
                ollama_url=settings.ollama_base_url,
            )

        unreal = UnrealIntegration(mcp=UnrealMCPClient(), native=WindowsNativeIntelligence())
        computer_driver = WindowsComputerControlDriver(armed=False)
        computer_control = ComputerControlService(
            permissions=agent.permissions or PermissionManager(),
            driver=computer_driver,
            require_checkpoint=True,
        )
        tools_controller = ToolsController(
            agent.permissions or PermissionManager(),
            workspaces_file=settings.data_dir / "workspaces.json",
            audit_file=settings.data_dir / "audit" / "audit.jsonl",
            terminal_file=settings.data_dir / "terminal.json",
            toggles_file=settings.data_dir / "agent_toggles.json",
            export_execution_reports=settings.export_execution_reports,
            reports_dir=settings.data_dir / "reports",
            unreal=unreal,
            computer_control_service=computer_control,
        )
        agent.set_tools_controller(tools_controller)

        try:
            from app.agent_runtime import UniversalAgentRuntime
            runtime = UniversalAgentRuntime(
                repo=PROJECT_ROOT,
                model=agent.provider.model_name or settings.model or "qwen3:8b",
                ollama_url=settings.ollama_base_url,
                permissions=agent.permissions,
            )
            agent.set_universal_runtime(runtime)
            LOGGER.info("Runtime universal: %s", runtime.status())
        except Exception:
            LOGGER.exception("Runtime universal indisponível; runtime nativo permanece ativo.")

        window = LumenWindow(
            root,
            agent,
            config_service=config_service,
            tools_controller=tools_controller,
            plugin_reports=plugin_reports,
            data_dir=settings.data_dir,
            mission_supervisor_factory=None if args.no_autonomous_mission_supervisor else mission_supervisor_factory,
        )
        window.run()
    finally:
        LOGGER.info("Lumen encerrada.")
    return 0


def tk_root():
    import tkinter as tk
    return tk.Tk()


if __name__ == "__main__":
    sys.exit(main())
