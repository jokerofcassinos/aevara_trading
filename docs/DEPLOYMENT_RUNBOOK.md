# @module: DEPLOYMENT_RUNBOOK
# @status: ACTIVE
# @last_update: 2026-04-10
# @summary: Manual de operações: promoção, rollback, troubleshooting e incident response.

# 🚀 AEVRA — DEPLOYMENT RUNBOOK

## 1. AMBIENTES E PROMOÇÃO
| Ambiente | Gate | Endpoint | Risk Cap |
|----------|------|----------|----------|
| **Dev** | Strict CI | Testnet | 10.0% |
| **Paper** | Full CI/CD | Live-Read | 4.8% |
| **Live** | Manual CEO | Live-Exec | 4.8% FTMO |

### Fluxo de Promoção
1. `push` para `main` dispara pipeline `aevara_ci_cd.yml`.
2. Validação de Gates (Lint, Unit, Integration, Property, Security).
3. Auto-deploy para `paper` via `DeployOrchestrator`.
4. Health Probe valida latência, drift e liveness.
5. CEO aprova via Telegram para promoção `live`.

## 2. ROLLBACK ATÔMICO
Em caso de falha no `HealthProbe` ou comando manual:
- **ID de Deploy**: ULID registrado no `deploy_orchestrator.log`.
- **Janela**: Atômica, concluída em < 30s.
- **Procedimento**:
  ```powershell
  python -m aevara.scripts.rollback_manager --deploy-id [ULID] --reason "FAULT"
  ```

## 3. INCIDENT RESPONSE
- **Drift Crítico**: Se `reconciliation_drift > 0.05`, o `HealthProbe` dispara `DEGRADED`. Avaliar logs do `ShadowSync`.
- **Latência P99**: Se > 45ms, reduzir carga ou otimizar persistência de telemetria.
- **DNA Mismatch**: Forçar `checkpoint_restore` via `ceo_remote_control`.

## 4. CONTATOS DE EMERGÊNCIA
- **CEO**: Alertado via Telegram (P0).
- **Audit Logs**: Localizados em `aevara/logs/deploy/`.
