"""Canonical autonomous mission specification for Lumen voice evolution.

The mission deliberately does not prescribe a particular STT/TTS vendor. The
autonomous evolution loop must research available options, obtain permitted
dependencies/assets when needed, implement, test, and retain evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VOICE_MISSION_ID = "LUMEN-VOICE-SELF-DEVELOPMENT"

VOICE_GOAL = """Lúmen deve desenvolver autonomamente, para si mesma e dentro da sua
interface atual, um sistema completo de conversação por voz semelhante ao modo
de voz de um assistente moderno.

A Lúmen deve pesquisar na internet e no próprio repositório as capacidades e
tecnologias necessárias, aprender com as evidências, identificar lacunas,
criar ou modificar ferramentas reutilizáveis, baixar/obter componentes e
dependências necessários quando isso for tecnicamente e legalmente apropriado,
escrever e modificar o código necessário dentro do projeto existente,
implementar a solução, adicionar testes, executar os testes, diagnosticar
falhas, pesquisar novamente quando necessário, corrigir e repetir até obter
evidência objetiva de funcionamento.

A experiência de voz deve usar uma voz feminina jovem, com idade vocal
percebida de no máximo 25 anos. Isso é uma característica estilística/percebida
da voz, não uma exigência de representar, imitar ou personificar uma pessoa
real menor de idade. A Lúmen deve pesquisar opções de TTS/voz que atendam a
esse requisito, considerando qualidade, licenciamento, uso local, latência,
dependências, possibilidade de download e integração. Não deve assumir
previamente um fornecedor ou biblioteca.

O resultado final deve permitir: ativar o modo de voz na própria UI; capturar
fala real do microfone; converter fala em texto; enviar esse texto pelo fluxo
normal de conversa da Lúmen; gerar uma resposta; converter a resposta em áudio
com a voz selecionada; reproduzir o áudio; manter conversas sucessivas; tratar
erros de microfone/reconhecimento/síntese/reprodução sem derrubar a UI; e
possuir testes automatizados para as camadas determinísticas.

A Lúmen deve poder pesquisar a internet para tirar dúvidas durante a evolução
e obter/baixar dependências, modelos, assets ou outros componentes necessários
quando permitido e apropriado. Deve preferir componentes locais, reutilizáveis
e mantíveis e preservar a cadeia de segurança existente.

A missão só pode ser marcada como concluída depois de verificar:
UI -> ativação -> captura -> STT -> Agent -> resposta -> TTS -> reprodução ->
conversa contínua. Existência de classes, imports, botões, dependências ou
testes isolados não constitui prova de conclusão. Falhas devem gerar
diagnóstico, pesquisa, evolução e nova validação, e não conclusão prematura."""

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
    "young_feminine_voice_requirement",
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
            "voice_profile": {
                "gender": "feminine",
                "maximum_perceived_age": 25,
                "note": (
                    "Stylistic/perceived characteristic; do not model or "
                    "impersonate a real minor."
                ),
            },
            "autonomous_research_permissions": {
                "web_research": True,
                "download_dependencies_or_assets_when_needed": True,
                "write_and_modify_project_code": True,
            },
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
