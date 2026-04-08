# ⚡ AEVRA — ACTIVATION RUNBOOK: Phase-Gated Sequence (Demo → Micro → Live)
## Status: ACTIVE | Profile: CEO + ExecutionLead + RiskOfficer
## Protocol: CCD-v2.0 + FTMO-Compliant (Ω-11) + Pilot Lock (0.01 lots)

---

## 🏛️ 1. PROTOCOLO DE ATIVAÇÃO

Este Runbook descreve o procedimento operacional padrão para a transição controlada do Aevra para capitais reais. Nenhuma fase pode ser ignorada. Nenhum gate pode ser violado. A trava de sizing de 0.01 lotes é imutável até a Fase 3.

### 🕒 Cronograma de Fases
| Fase | Ambiente | Sizing | Duração Mínima | Gate de Saída |
|------|----------|--------|----------------|---------------|
| **F1: Demo Validation** | FTMO Demo | 0.01 | 24-48h (50 trades) | CEO `/go_live_micro` |
| **F2: Micro-Live** | Real ($100) | 0.01 | 7-14 dias | CEO `/enable_scaling` |
| **F3: Scaling & Ergodic** | Real (Full) | Adaptive | Contínuo | Sharpe > 2.0 (Steps) |

---

## 🛠️ 2. SETUP E INICIALIZAÇÃO

### 2.1 Preparação de Ambiente
1. **MT5**: Conexão estável com ping < 20ms para o servidor da corretora.
2. **Dashboard**: Abrir `aevara/src/telemetry/ftmo_dashboard.py`.
3. **PowerShell**: Abrir como Administrador.

### 2.2 Comando de Inicialização (Exemplo Fase 1)
```powershell
# Inicia em modo Demo para validação basal
.\aevara\scripts\run_activation_sequence.ps1 -Phase demo -Symbols "BTC,ETH,SOL" -MaxDDPct 4.0
```

---

## 🛡️ 3. MONITORAMENTO E PORTÕES (GATES)

### 3.1 Métricas Críticas (Hot-Watch)
- **Latência (p99)**: ≤ 50ms (Decision -> MT5 Deal).
- **Reconciliation Drift**: ≤ 0.01% (Sync a cada 3s).
- **FTMO Limit**: Daily DD -4% Max. Global DD -8% Max.
- **Pilot Stability**: Score ≥ 0.90 após 50 trades.

### 3.2 Gate de Promoção de Fase
Para avançar, todos os critérios técnicos devem ser [x]. O CEO deve então digitar o comando no CLI:
- `/go_live_demo` (IDLE -> F1)
- `/go_live_micro` (F1 -> F2)
- `/enable_scaling` (F2 -> F3)

---

## 🚨 4. RESPOSTA A INCIDENTES E ROLLBACK

### 4.1 Cenários de Alerta P0
| Incidente | Ação Aevra | Ação Manual (CEO) |
|-----------|-----------|------------------|
| **Slippage > 1%** | `/pause` automático | Investigar liquidez config |
| **Connection Loss** | `emergency_halt()` em 500ms | Reiniciar MT5 Bridge |
| **Drift > 0.01%** | Auto-Reconciliação | Conferir ordens manuais |
| **FTMO Alert** | **HARD FREEZE** | Encerrar ciclo mensal |

### 4.2 Protocolo de Rollback
Se instabilidade detectada na Fase 2 ou 3:
1. Executar `/pause`.
2. Encerrar todas as ordens abertas.
3. Retornar para Fase 1 (Demo) com `reset_parameters=true`.

---

## 🏁 5. CHECKLIST FINAL DE GO-LIVE
- [ ] MT5 Adapter reconciliando em 3s.
- [ ] Pilot Controller travado em 0.01 lotes (Sizing Lock).
- [ ] FTMO Guard ativo e buffers 4%/8% verificados.
- [ ] Telemetria streaming para o Painel de Ativação.
- [ ] Chave HMAC do CEO carregada e validada.

**Ativação Iniciada. Aevra está em MODO DEMO.** 🃏⚡🛡️
