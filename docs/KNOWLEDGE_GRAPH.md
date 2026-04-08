# @module: KNOWLEDGE_GRAPH
# @deps: AEVRA_DIRECTIVE.md
# @status: INITIALIZED
# @last_update: 2026-04-06
# @summary: Grafo de conceitos, modulos, relacoes e licoes aprendidas - Anti-duplicacao

**Formato**: `[Node] --(relacao)--> [Node]` com metadata de contexto.

---

## NOS CONCEITUAIS (Conceitos Fundamentais)

- `C001: LogOdds Aggregation` --(principio)--> `Phi0: Zero-dependencia humana`
- `C002: Microstructure` --(principio)--> `Phi3: Microestrutura prioridade`
- `C003: Adaptabilidade` --(principio)--> `Phi6: DNA parametrico`
- `C004: Observabilidade` --(principio)--> `Phi9: Observabilidade total`
- `C005: Robustez` --(principio)--> `Phi7: Robustez adversarial`
- `C006: Anti-amnesia` --(principio)--> `Phi8: Memoria persistente`

## NOS MODULARES
- `M001: DataSovereign` --(depende)--> `C002: Microstructure`
- `M002: MemorySystem` --(depende)--> `C006: Anti-amnesia`
- `M003: QROE Orchestrator` --(depende)--> `C003: Adaptabilidade`
- `M004: ValidationForge` --(depende)--> `C001: LogOdds Aggregation`
- `M005: PhantomEngine` --(depende)--> `C003: Adaptabilidade`
- `M006: TelemetryMatrix` --(depende)--> `C004: Observabilidade`
- `M007: ZeroTrustOps` --(depende)--> `C005: Robustez`
- `M008: LifecycleOrchestrator` --(depende)--> `C003: Adaptabilidade`
- `M010: RiskEngine` --(depende)--> `C001: LogOdds Aggregation`
- `M016: LiveExecutionGateway` --(depende)--> `C005: Robustez`
- `M017: E2EOrchestrator` --(centraliza)--> `TODOS_SUBSISTEMAS`
- `M018: ShadowSync` --(valida)--> `M005: PhantomEngine`
- `M019: LatencyProfiler` --(monitora)--> `M017`
- `M020: StateReconciler` --(valida)--> `M017`
- `M021: TelegramBridge` --(recebe_cmd)--> `C006: Simbiose CEO`
- `M022: AlertRouter` --(filtra)--> `M021`
- `M023: DashboardFeed` --(publica)--> `M006: TelemetryDashboard`
- `M024: OCLParser` --(decodifica)--> `M017`
- `M025: AdversarialEngine` --(estressa)--> `M017`
- `M026: MonteCarloSimulator` --(simula)--> `M004: ValidationForge`
- `M027: AlphaValidator` --(audita)--> `M004`
- `M028: PerformanceProfiler` --(monitora)--> `M017`, `M006`
- `M029: PilotController` --(gerencia)--> `M016: LiveExecution`
- `M030: FTMOGuard` --(bloqueia)--> `M016`
- `M031: TelemetryStream` --(monitora)--> `M029`, `M016`
- `M032: FailoverManager` --(suporta)--> `M029`
- `M033: AdaptiveScalingEngine` --(otimiza_g)--> `M029: PilotController`
- `M034: CapitalAllocator` --(agenda)--> `M029`
- `M035: LiveEdgeMonitor` --(valida)--> `M034`
- `M036: DynamicCircuitBreakers` --(interrompe)--> `M029`
- `M037: MT5Adapter` --(traduz)--> `M016: LiveExecution`
- `M038: AevraExpert` --(executa)--> `MT5_TERMINAL`
- `M039: HMAC_Verifier` --(veta_pelo_secret)--> `M037`
- `M040: SocketBridge` --(conecta)--> `M037`, `M038`
- `M041: CrossAssetEngine` --(extrai_TE)--> `M001: Data_Ring`
- `M042: MultiStrategyAllocator` --(Thompson_Sampling)--> `M017: Orchestrator`
- `M043: PortfolioRiskGuard` --(enforce_ρ_CVaR)--> `M042`
- `M044: AsyncRebalancer` --(corrige_drift)--> `M037`
- `M045: FTMOManager` --(hard_block)--> `M016: LiveExecution`
- `M046: LiveConnector` --(reconcilia_3s)--> `M037`
- `M047: PilotController` --(lock_0_01)--> `M046`
- `M048: FTMODashboard` --(exibe_health)--> `M045`
- `M049: PostTradeAnalyzer` --(forense_12_camadas)--> `M016`
- `M050: BayesianCalibrator` --(recalibra_priors)--> `M002: DNA_Storage`
- `M051: AdaptiveThresholds` --(ajusta_θ)--> `M017: Orchestrator`
- `M052: SelfDiagnosis` --(auto_healing)--> `M043: RiskGuard`
- `M053: KGRefinement` --(sugere_conexões)--> `M022: KG_Brain`
- `M054: MultiAssetRouter` --(roteia_ETH_SOL)--> `M037: MT5Adapter`
- `M055: CrossAssetCorrelator` --(map_TE_BTC_ETH)--> `M054`
- `M056: FTMOMultiAssetGuard` --(Σ_lots_5.0)--> `M054`
- `M057: AssetSpecificFeatures` --(vol_scaling_sessão)--> `M055`
- `M058: StochasticSizer` --(kelly_bayesian)--> `M002: DNA_Storage`
- `M059: PortfolioOptimizer` --(maximiza_g)--> `M058`
- `M060: ConstraintEnforcer` --(projeção_L1)--> `M056`
- `M061: SizingTelemetry` --(compliance_drag)--> `M044: AlertRouter`
- `M062: ActivationOrchestrator` --(gerencia_phases)--> `M017: Orchestrator`
- `M063: PilotController` --(lock_sizing_0_01)--> `M062`
- `M064: TelemetryActivation` --(monitoring_live)--> `M048`

## RELACOES CRUZADAS
- `M001` --(alimenta)--> `M004`, `M010`, `M016`
- `M002` --(alimenta)--> `TODOS_MODULOS`
- `M017` --(orquestra)--> `M003`, `M004`, `M005`, `M010`, `M016`
- `M017` --(comunicado_via)--> `M021`, `M023`
- `M022` --(gerencia_prioridade)--> `M021`
- `M021` --(usa)--> `M024: OCLParser`
- `M025` --(valida_robustez)--> `M017`
- `M027` --(penaliza_p_valor)--> `M004`
- `M026` --(calcula_cvar)--> `M004`
- `M030: FTMOGuard` --(protege)--> `EQUITY_AEVRA`
- `M029: PilotController` --(escala)--> `RISK_EXPOSURE`
- `M033: ScalingEngine` --(recebe_posterior)--> `M002: DNA_Storage`
- `M037: MT5Adapter` --(atômico)--> `MT5_DEAL_SERVER`
- `M045: FTMOManager` --(monitora)--> `MT5_ACCOUNT_REST`
- `M042: Allocator` --(consome_transfer_entropy)--> `M041`
- `M049: Analyzer` --(alimenta_priors)--> `M050`
- `M054: Router` --(bounded_queue_500)--> `M016`
- `M058: Sizer` --(penaliza_CVaR)--> `M050`
- `M062: Activation` --(ceo_commands)--> `CLI_INTERFACE`
- `M065: AntigravityPhoneConnect` --(monitora)--> `AEVRA_COGNITIVE_CORE`

## LICOES APRENDIDAS
- Nenhuma licao registrada ainda (sistema em boot).

## ISOLATED NODES (Sem conexao - requer atencao)
- Nenhuma no isolado detectado.
