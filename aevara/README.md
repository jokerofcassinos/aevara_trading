# Aevra

Autonomous quantitative trading system — adaptive signal fusion, DNA-driven meta-learning, and institutional-grade execution.

**Status**: Research & Development | **Tests**: 529 passing | **Tasks**: T-001 through T-013

---

## Architecture

```
src/
├── core/
│   ├── coherence/          Log-odds signal fusion (L_total = Σ w_i · L_i)
│   └── dna/                Meta-learning weights with shadow promotion
├── orchestrator/           QROE — Quantum Rotational Orchestration Engine
├── agents/regime/          Market regime detection (HMM + entropy)
├── data/
│   ├── ingestion/          Timestamp sync, ring buffers, feature pipeline
│   └── schemas/            Strict market tick contracts
├── phantom/                Counterfactual simulation + alignment tracking
├── risk/
│   ├── gates.py            Dynamic vetos, CVaR sizing, correlation caps
│   └── position_sizing.py  Kelly fractional, volatility-scaled, cVAR-bounded
├── execution/
│   ├── lifecycle.py        Strict order state machine (7 states, 0 drift)
│   ├── sor.py              Smart Order Router — TCE-gated venue selection
│   ├── algorithms.py       TWAP / VWAP / POV / Iceberg execution
│   └── reconciler.py       Async state reconciliation vs exchange
├── validation/
│   ├── cpcv_pipeline.py    Combinatorial Purged Cross-Validation
│   ├── deflated_sharpe.py  DSR, MinBTL, PBO — avoid overfitting
│   ├── walk_forward.py     Walk-forward analysis with regime stratification
│   └── adversarial_injector.py  GAN-driven stress testing
├── infra/
│   ├── security/           Credential vault — zero plaintext exposure
│   ├── resilience/         Circuit breaker + rate limiter
│   └── execution/          Idempotent order engine
├── telemetry/              Structured JSON logging + Brier calibration
├── memory/                 Knowledge graph + context library with decay
└── dna/                    DNA engine — online weight adaptation, promotion gates

scripts/
└── github_sync.py          Selective staging, atomic commits, telemetry, rollback
```

## Quickstart

```powershell
# Clone
git clone https://github.com/jokerofcassinos/aevara_trading.git
cd aevara_trading

# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests/ --ignore=tests/integration -v

# Dry-run sync
python scripts/github_sync.py --dry-run
```

## Key Invariants

| Invariant | Guarantee |
|-----------|-----------|
| Log-odds fusion | All signals aggregated via L = Σ(w_i · L_i) + prior |
| Risk gate first | Vetos enforced BEFORE any execution |
| Idempotent operations | Every retryable operation is idempotent |
| Zero hardcoded thresholds | All parameters tunable via DNA |
| Phantom async non-blocking | Ghost simulation never blocks decision loop |
| Schema validation | No module accepts unvalidated input |

## Modules Status

| Module | Tests | Status |
|--------|-------|--------|
| Coherence Engine | 16+ | Implemented |
| QROE Orchestrator | 40+ | Implemented |
| Phantom Engine | 50+ | Implemented |
| DNA Meta-Learning | 45+ | Implemented |
| Memory Subsystem | 25+ | Implemented |
| Risk Engine | 60+ | Implemented |
| Validation Forge | 65+ | Implemented |
| Telemetry | 30+ | Implemented |
| Infra (ZeroTrust) | 75+ | Implemented |
| Execution Engine | 102+ | Implemented |
| GitHub Sync | 37+ | Implemented |

## GitHub Sync

```powershell
# Check what would be synced (dry run)
python scripts/github_sync.py --dry-run

# Execute full pipeline with commit and push
python scripts/github_sync.py --execute

# Custom remote and branch
python scripts/github_sync.py --execute --repo-url https://github.com/org/repo.git --branch dev
```

Authentication (set one before `--execute`):
- `AEVRA_GITHUB_PAT` environment variable
- SSH key at `~/.ssh/aevara_ed25519`
- GitHub CLI (`gh auth login`)

## Design Principles

- **Coherence over accuracy**: Calibrated confidence beats raw precision
- **Adaptation over prediction**: Evolve with the market, don't forecast it
- **Survival over profit**: Risk gates are non-negotiable
- **Evidence over belief**: Everything is validated via CPCV + DSR + PBO
- **Transparency over complexity**: Every decision is logged, traceable, auditable

## License

Confidential — All rights reserved.
