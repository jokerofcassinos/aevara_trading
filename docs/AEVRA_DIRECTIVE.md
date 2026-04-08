---
name: AEVRA_DIRECTIVE
description: Constitution imutavel do projeto Aevra - Principios, invariantes e protocolos fundamentais
type: project
---
# AEVRA DIRECTIVE v2.0
# @module: CCD-v2.0 Core Directive
# @deps: None (base constitution)
# @status: ACTIVE
# @last_update: 2026-04-06
# @summary: Constituicao imutavel definindo principios, invariantes arquiteturais, protocolos de memoria e qualidade institucional.

## INARIANTES ARQUITETURAIS (Nunca Violados)
1. Coerencia em log-odds: todo sinal agregado via L_total = Sigma(w_i * L_i) + prior
2. Thresholds mutaveis: nenhum parametro hardcoded; todos ajustaveis via DNA
3. PhantomEngine assincrono: nunca bloqueia loop principal de decisao
4. Auditoria dupla: logs estruturados para trades executados E vetos
5. Risk gate primeiro: vetos dinamicos aplicados ANTES de qualquer execucao
6. Schema validation: nenhum modulo aceita dados nao validados
7. Idempotencia: toda operacao retryable e idempotente por design

## PRINCIPIOS DE QUALIDADE (Invariantes)
- Zero simplificacoes, zero placeholders, zero "em producao faremos diferente"
- Cada arquivo e entregue completo, testado, documentado e integrado
- Context drift = falha de protocolo. Arquitetura violada = rejeicao automatica.
- Anti-amnesia formal: rastreabilidade causal total, decaimento controlado

## PHI-PRINCIPLES (Phi0-Phi12)
- Phi0: Zero dependencia de intervencao humana para evolucao tecnica
- Phi1: Impacto nao-linear de latencia
- Phi2: Feature engineering com validade garantida
- Phi3: Microestrutura de mercado como prioridade
- Phi4: Roteamento contextual multi-agente
- Phi5: Execucao soberana com verificacao dupla
- Phi6: Adaptacao continua de DNA parametrico
- Phi7: Robustez adversarial nativa
- Phi8: Memoria persistente e anti-entropica
- Phi9: Observabilidade total em tempo real
- Phi10: Risk-adjusted returns como metrica primaria
- Phi11: Lifecycle orchestration com zero downtime
- Phi12: Anti-fragilidade sistematica

## GATES DE VALIDACAO (Pre-Integration)
| Gate | Criterio | Metrica de Passagem |
|------|----------|-------------------|
| G1: Schema Integrity | 100% contratos validados em runtime | Zero SchemaValidationError em 10k iteracoes |
| G2: Phantom Fidelity | Ghost vs Real alignment >= 0.82 | corr(RR_ghost, RR_real) >= 0.82 em 5 regimes |
| G3: Coherence Stability | C2 nao colapsa em transicao | std(C2) < 0.15 durante regime shift |
| G4: Risk Gate Efficacy | DD nunca viola FTMO hard limit | max_drawdown <= 4.8% em 1000 simulacoes |

## REGRAS DE COMUNICACAO (OCE-TE)
- Zero afirmacoes vagas. Quantificacao universal.
- Input "a gente" -> Output "nos"/"a equipe"/"o sistema"
- Zero emojis sem solicitacao explicita do CEO
- Formato: Contexto -> Problema -> Analise -> Solucao -> Acao -> Verificacao
