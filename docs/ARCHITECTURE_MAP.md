# @module: ARCHITECTURE_MAP
# @deps: AEVRA_DIRECTIVE.md, PROJECT_STATE.yaml
# @status: INITIALIZED
# @last_update: 2026-04-06
# @summary: Mapa de dependencias, contratos e fluxo de dados entre modulos

## FLOW
```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  DATA FEEDS  │───▶│  DATA        │───▶│  FEATURE     │
│  (WS/REST)   │    │  SOVEREIGN   │    │  ENGENEERING │
└──────────────┘    └──────────────┘    └──────┬───────┘
                                                │
                    ┌──────────────┐    ┌───────▼───────┐
                    │  EXECUTOR    │◄───│  RISK        │
                    │  (ORDERS)    │    │  ENGINE      │
                    └──────┬───────┘    └──────┬──────┘
                           │                   │
┌──────────────┐    ┌──────▼───────┐    ┌──────▼───────┐
│  PHANTOM     │    │  ORCHESTR    │    │  VALIDATION  │
│  ENGINE      │◄───│  (QROE)      │───▶│  FORGE       │
└──────────────┘    └──────┬───────┘    └──────────────┘
                           │
┌──────────────┐    ┌──────▼───────┐    ┌──────────────┐
│  TELEMETRY   │    │  MEMORY      │    │  LIFECYCLE   │
│  MATRIX      │◄───│  SYSTEM      │    │  ORCHESTRATOR│
└──────────────┘    └──────────────┘    └──────────────┘
```

## DEPENDENCY MATRIX

| Modulo | Depende de | Fornece para | Contrato de I/O |
|--------|------------|--------------|-----------------|
| DataSovereign | Exchange APIs | FeatureEng, ValidationForge, RiskEngine | `SignalBatch (checksummed, synced)` |
| MemorySystem | None | Todos os modulos | `StateQuery ↔ StateResponse` |
| QROE Orchestrator | MemorySystem | Pipeline flow | `TaskInput ↔ StatePatch` |
| ValidationForge | DataSovereign | DNA promotion | `BacktestResult ↔ PromotionDecison` |
| PhantomEngine | DataSovereign, MemorySystem | Orchestrator | `GhostSignal ↔ AlignmentScore` |
| TelemetryMatrix | Orchestrator | CEO dashboard, alerts | `TraceEvent ↔ AlertAction` |
| ZeroTrustOps | None | Executer, RiskEngine | `CredRef ↔ AuthToken` |
| LifecycleOrchestrator | ValidationForge, PhantomEngine | Deploy pipeline | `ModeSwitch ↔ StateMigration` |
| AdversarialForge | ValidationForge | RiskEngine, Testing | `StressScenario ↔ RobustnessScore` |
| RiskEngine | DataSovereign, ValidationForge | Executor | `PositionOrder ↔ VetoDecision` |

## CONTRATO GLOBAL DE DADOS

### Schema Base
```
Signal:
  timestamp: unix_ns (synchronized)
  feature: dict[str, float] (normalized, validated)
  regime: str (HMM state)
  confidence: float [0, 1]
  checksum: crc32
  
Decision:
  task_id: str
  action: [OPEN_LON, OPEN_SHORT, CLOSE, HOLD]
  size: float (% of capital)
  confidence: float
  veto_override: bool
  trace_id: str (for telemetry)
```
