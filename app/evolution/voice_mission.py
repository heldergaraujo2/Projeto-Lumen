"""Canonical autonomous mission specification for Lumen voice evolution.

This module defines the objective; it does not prescribe a particular STT/TTS
vendor. The autonomous evolution loop must research the available local
options, select an appropriate implementation, build it, test it, and retain
evidence before declaring the mission complete.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VOICE_MISSION_ID = "LUMEN-VOICE-SELF-DEVELOPMENT"

VOICE_GOAL = """Lúmen deve desenvolver autonomamente, para si mesma e dentro da sua
interface atual, um sistema completo de conversação por voz semelhante ao modo
de voz de um assistente moderno. A Lúmen deve receber esta missão como um
objetivo de evolução, pesquisar na web e no próprio repositório as capacidades
e tecnologias necessárias, aprender com as evidências, identificar lacunas,
criar ou modificar ferramentas reutilizáveis, implementar a solução, adicionar
testes, executar os testes, diagnosticar falhas, pesquisar novamente quando
necessário, corrigir e repetir até obter evidência objetiva de funcionamento.

O resultado final deve permitir: ativar o modo de voz na própria UI; capturar
fala real do microfone; converter fala em texto; enviar esse texto pelo fluxo
normal de conversa da Lúmen; gerar uma resposta; converter a resposta em áudio;
reproduzir o áudio ao usuário; manter conversas sucessivas; tratar erros de
microfone/reconhecimento/síntese/reprodução sem derrubar a UI; e possuir testes
automatizados para as camadas determinísticas.

A Lúmen NÃO deve assumir previamente uma biblioteca específica de STT ou TTS.
Ela deve pesquisar e justificar a escolha técnica com base no ambiente local,
licenciamento, dependências, desempenho e integração com a arquitetura
existente. Deve preferir componentes locais e reutilizáveis e preservar a
cadeia de segurança existente.

A missão só pode ser marcada como concluída depois de verificar cada etapa:
UI -> ativação -> captura -> STT -> Agent -> resposta -> TTS -> reprodução ->
conversa contínua. Existência de classes, imports, botões ou testes isolados
não constitui prova de conclusão. Falhas devem gerar pesquisa, evolução e
nova validação, e não conclusão prematura."""

VOICE_ACCEPTANCE_CRITERIA = (
    "voice_ui_activation",
    "microphone_capture",
    "speech_to_text",
    "agent_conversation",
    "text_to_speech",
    "audio_playback",
    "continuous_voice_turns",
    "voice_error_recovery",
    "automated_voice_regressions",
)


@dataclass(frozen=True)
class VoiceMissionSpec:
    mission_id: str = VOICE_MISSION_ID
    goal: str = VOICE_GOAL
    requires_unreal: bool = False
    acceptance_criteria: tuple[str, ...] = VOICE_ACCEPTANCE_CRITERIA

    def planner_context(self) -> dict[str, Any]:
        return {
            "mission_type": "voice_self_development",
            "requires_unreal": self.requires_unreal,
            "acceptance_criteria": list(self.acceptance_criteria),
            "completion_rule": (
                "Do not finish from source existence alone. Each criterion "
                "requires concrete implementation/test evidence; real "
                "microphone/audio behavior must be validated on the user's PC."
            ),
        }

    def missing_criteria(self, evidence: dict[str, Any] | None = None) -> tuple[str, ...]:
        evidence = evidence or {}
        return tuple(
            criterion
            for criterion in self.acceptance_criteria
            if not bool(evidence.get(criterion))
        )

    def is_complete(self, evidence: dict[str, Any] | None = None) -> bool:
        return not self.missing_criteria(evidence)
