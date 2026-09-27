# F18 — Model Adaptation Laboratory

## Objetivo

F18 cria um laboratório isolado para pesquisar e comparar adaptações da camada de
modelos sem alterar o runtime estável da Lumen.

Escopo:
- LoRA/adapters;
- fine-tuning;
- distillation;
- pruning;
- quantization;
- curadoria e geração de datasets;
- curriculum;
- tool-use/domain adaptation;
- otimização de inferência.

## Limite de autoridade

F18 não treina, executa inferência, baixa modelos, acessa rede ou faz deploy.
Recebe resultados produzidos por uma integração autorizada e registra evidência
reprodutível. Assim, não cria uma nova superfície de execução fora das barreiras
existentes.

Fluxo:

Limitação observada
  -> AdaptationSpec
  -> DatasetSpec + ExperimentDesign
  -> Workspace isolado
  -> Resultado fornecido por executor autorizado
  -> AdaptationEvidence
  -> Candidate
  -> Benchmark
  -> Regression + Safety
  -> Promotion Gate (F15)

## Contratos

- DatasetSpec: identidade/versionamento, tamanho, splits e hash opcional.
- AdaptationSpec: modelo base, alvo, tipo de adaptação, camadas, métrica,
  workspace, risco, seed e configuração.
- AdaptationExperiment: desenho reprodutível e limites declarativos.
- AdaptationEvidence: resultado com seed, amostra, artefatos, testes e chave
  de reprodutibilidade.
- AdaptationCandidate: candidato isolado convertido ao contrato F12/F15.
- AdaptationEvaluator: comparação e digest determinístico.
- ModelAdaptationLab: registro, validação, benchmark, regressão e segurança.

## Segurança

1. Workspace precisa estar sob evolution-lab/.
2. Candidato precisa permanecer isolado.
3. Evidência é obrigatória antes do candidato.
4. Artefatos e testes são obrigatórios para evidência.
5. Regressão impede elegibilidade.
6. Componentes protegidos continuam sob SafetyValidator.
7. Risco alto continua exigindo aprovação humana.
8. Nenhum método de execução de modelo, processo, rede, deploy ou alteração
   de permissões existe nesta camada.
9. Promoção continua sendo responsabilidade do PromotionGate F15.

## Critério de conclusão

F18 é concluída quando contratos, isolamento, evidência, benchmark, regressão,
segurança, testes automatizados e documentação estiverem validados no CI.
