"""Universal agent runtime built from existing agent frameworks.

OpenAI Agents SDK is the orchestration layer. OpenHands is the coding/workspace
specialist. Browser Use is the browser specialist. All three are optional
dependencies so the native Lumen runtime remains importable if they are absent.

The runtime never silently grants capabilities:
- browser research requires WEB_ACCESS;
- browser actions require COMPUTER_CONTROL;
- repository modification requires WRITE + TERMINAL.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RuntimeResult:
    text: str
    runtime: str
    used_tools: tuple[str, ...] = ()
    verified: bool = False


class UniversalAgentRuntime:
    """Routes open-ended natural-language tasks to specialized agent runtimes."""

    def __init__(
        self,
        *,
        repo: str | Path,
        model: str,
        ollama_url: str,
        permissions: Any = None,
    ) -> None:
        self.repo = Path(repo)
        self.model = model
        self.ollama_url = ollama_url.rstrip("/")
        self.permissions = permissions

    @staticmethod
    def _importable(module: str) -> bool:
        try:
            __import__(module)
        except Exception:
            return False
        return True

    def status(self) -> dict[str, bool]:
        return {
            "openai_agents": self._importable("agents"),
            "openhands": self._importable("openhands"),
            "browser_use": self._importable("browser_use"),
        }

    def available(self) -> bool:
        return self._importable("agents")

    def _granted(self, level_name: str) -> bool:
        if self.permissions is None:
            return False
        try:
            from app.security.permissions import PermissionLevel

            return bool(self.permissions.is_granted(getattr(PermissionLevel, level_name)))
        except Exception:
            return False

    def _run(self, coroutine):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)
        raise RuntimeError("UniversalAgentRuntime must run outside an active event loop")

    def run(self, task: str) -> RuntimeResult | None:
        """Run one open-ended user task through the universal agent router."""
        if not task.strip() or not self.available():
            return None
        return self._run(self._run_async(task.strip()))

    async def _run_async(self, task: str) -> RuntimeResult | None:
        from openai import AsyncOpenAI
        from agents import (
            Agent,
            OpenAIChatCompletionsModel,
            Runner,
            function_tool,
            set_tracing_disabled,
        )

        set_tracing_disabled(True)
        client = AsyncOpenAI(
            base_url=f"{self.ollama_url}/v1",
            api_key="ollama",
        )
        model = OpenAIChatCompletionsModel(
            model=self.model,
            openai_client=client,
        )

        @function_tool
        async def delegate_to_openhands(instruction: str) -> str:
            """Use OpenHands for repository/code tasks requiring edits or tests."""
            if not self._granted("WRITE") or not self._granted("TERMINAL"):
                return (
                    "BLOQUEADO: evolução de código exige as permissões WRITE e "
                    "TERMINAL na política da Lúmen."
                )
            try:
                return await asyncio.to_thread(self._run_openhands, instruction)
            except Exception as exc:
                return f"OpenHands falhou de forma controlada: {type(exc).__name__}: {exc}"

        @function_tool
        async def delegate_to_browser_use(instruction: str) -> str:
            """Use Browser Use for live web research or browser interaction."""
            if not self._granted("WEB_ACCESS"):
                return "BLOQUEADO: esta tarefa exige WEB_ACCESS."
            lowered = instruction.lower()
            mutation_words = (
                "enviar", "encontre o contato", "digite", "clique",
                "compre", "publique", "post", "delete", "exclua",
                "mensagem", "whatsapp", "login", "faça login",
            )
            if any(word in lowered for word in mutation_words) and not self._granted(
                "COMPUTER_CONTROL"
            ):
                return (
                    "BLOQUEADO: a tarefa parece alterar uma aplicação/conta. "
                    "Ela exige COMPUTER_CONTROL e aprovação pelas políticas da Lúmen."
                )
            try:
                return await self._run_browser_use(instruction)
            except Exception as exc:
                return f"Browser Use falhou de forma controlada: {type(exc).__name__}: {exc}"

        router = Agent(
            name="Lumen Universal Agent",
            instructions=(
                "Você é o executor universal da Lúmen. Receba o objetivo do usuário "
                "em linguagem natural e escolha a melhor forma de concluí-lo. "
                "Você tem dois especialistas: delegate_to_browser_use para pesquisa "
                "Web e interação real com navegador; delegate_to_openhands para "
                "alterações de código, arquivos, testes e tarefas de engenharia. "
                "Para perguntas puramente explicativas, responda diretamente. "
                "Para tarefas que exigem ação, prefira delegar em vez de inventar "
                "uma solução. Depois de uma delegação, use o resultado como evidência. "
                "Nunca diga que uma ação foi executada se a ferramenta informou "
                "BLOQUEADO ou falhou. Se uma capacidade estiver ausente, explique "
                "a lacuna objetivamente."
            ),
            model=model,
            tools=[delegate_to_openhands, delegate_to_browser_use],
        )
        result = await Runner.run(router, task)
        output = str(result.final_output or "").strip()
        if not output:
            return None
        return RuntimeResult(
            text=output,
            runtime="openai-agents",
            used_tools=tuple(
                getattr(item, "name", "")
                for item in getattr(result, "new_items", [])
                if getattr(item, "name", "")
            ),
            verified=True,
        )

    def _run_openhands(self, instruction: str) -> str:
        from pydantic import SecretStr
        from openhands.sdk import LLM, Agent, Conversation
        from openhands.sdk.tool import Tool
        from openhands.tools.file_editor import FileEditorTool
        from openhands.tools.terminal import TerminalTool

        llm = LLM(
            usage_id="lumen-universal",
            model=f"ollama/{self.model}",
            api_key=SecretStr("ollama"),
            base_url=self.ollama_url,
            native_tool_calling=False,
            timeout=300,
        )
        tools = [
            Tool(name=TerminalTool.name),
            Tool(name=FileEditorTool.name),
        ]
        agent = Agent(llm=llm, tools=tools)
        conversation = Conversation(agent=agent, workspace=str(self.repo))
        conversation.send_message(
            "Trabalhe somente no workspace autorizado da Lúmen. "
            "Execute a tarefa, valide o resultado e não declare sucesso sem evidência.\n\n"
            + instruction
        )
        conversation.run()
        return (
            "OpenHands concluiu o ciclo de trabalho no workspace autorizado. "
            "A alteração/teste foi processado pelo runtime especializado; "
            "a Lúmen deve verificar os artefatos e testes antes de considerar o objetivo concluído."
        )

    async def _run_browser_use(self, instruction: str) -> str:
        try:
            from browser_use import Agent as BrowserAgent
            from browser_use.llm import ChatOllama
        except ImportError:
            from browser_use import Agent as BrowserAgent, ChatOllama

        llm = ChatOllama(model=self.model, base_url=self.ollama_url)
        agent = BrowserAgent(task=instruction, llm=llm)
        history = await agent.run()
        result = history.final_result()
        return str(result or "Browser Use terminou sem resultado textual.")
