# @module: LIVE_PILOT_RUNBOOK
# @status: ACTIVE
# @last_update: 2026-04-10
# @summary: Procedimento de ativação, monitoramento, resposta a incidentes e rollback para o Pilot Sizing.

# 🚀 AEVRA — LIVE PILOT RUNBOOK (T-021)

## 1. PROCEDIMENTO DE ATIVAÇÃO
1. **Verificação de Credenciais**: Garantir que as API Keys (Live/Paper) estão cifradas e acessíveis via `CredentialVault`.
2. **Setup FTMO**: Validar saldo inicial e thresholds de drawdown dinâmico.
3. **Comando de Ativação**:
   ```powershell
   ./aevara/scripts/run_live_pilot.ps1 -mode pilot -max_allocation_pct 30
   ```
4. **Verificação de Sync**: Dashboard deve mostrar `PILOT_INIT` e `allocation_pct: 10%`.

## 2. REGRAS DE ESCALONAMENTO (SCALING)
| Condição | Ação |
|----------|------|
| `live_sharpe >= 1.5` (50 trades) | `scale_allocation INCREASE` (+5%) |
| `max_drawdown > 1.0%` | `scale_allocation DECREASE` (-5%) |
| `ftmo_violation == True` | `emergency_halt HALT` (Immediate) |
| `manual_switch == STOP` | `emergency_halt HALT` (Immediate) |

## 3. RESPOSTA A INCIDENTES
- **Drift de Reconciliação (>0.01%)**: O `FailoverManager` emitirá alerta `CRITICAL`. Sistema entra em `graceful_degradation`.
- **Latency Spike (>500ms)**: Freeze automático de novas ordens até estabilização.
- **Exchange Outage (503/403)**: `emergency_halt` disparado por `FTMOGuard` ou `LiveGateway`.

## 4. ROLLBACK E REVERSÃO
- Em caso de falha sistêmica, o `FailoverManager` congela o estado e fecha todas as posições abertas (`flatten`).
- Relatório de incidentes gerido em `aevara/logs/live/`.
- CEO recebe alerta P0 via Telegram em < 1s.

**O primeiro trade real é o teste final de integridade. Monitore com rigor.** 🏛️💹⚡🛡️
