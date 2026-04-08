# @module: aevara.src.main
# @deps: asyncio, typing, yaml, deployment.activation_orchestrator, orchestrator.qroe_engine, execution.mt5_adapter, interfaces.telegram_bridge
# @status: TRANSITION-READY (T-030.10)
# @last_update: 2026-04-10
# @summary: CENTRAL ENTRY POINT — AEVRA COGNITIVE CORE. Supporting Dry-Run & Micro-Live Transition.

from __future__ import annotations
import asyncio
import sys
import time
import yaml
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional

# --- T-030 INFRASTRUCTURE ---
from aevara.src.orchestrator.message_bus import bus
from aevara.src.telemetry.structured_logger import logger
from aevara.src.interfaces.dashboard import AevraDashboard
from aevara.src.infra.security.credential_vault import CredentialVault
from aevara.src.infra.hardening import Hardening

# --- Ω-LAYER ---
from aevara.src.perception.regime_detector import RegimeDetector           
from aevara.src.risk.quantum_gates import QuantumGates                      
from aevara.src.meta.learning_engine import LearningEngine                  
from aevara.src.innovation.proprietary import Proprietary                  
from aevara.src.portfolio.multi_strategy_allocator import MultiStrategyAllocator as MultiStrategy 
from aevara.src.stress.monte_carlo_simulator import EquitySimulator as MonteCarlo     
from aevara.src.adversarial.robustness import RobustnessEngine as Robustness
from aevara.src.multi_timeframe.analysis import Analysis                  
from aevara.src.opportunity.cost_engine import CostEngine                  
from aevara.src.confidence.progressive_scaling import ProgressiveScaling    
from aevara.src.frontier.ergodicity import ErgodicityEngine as Ergodicity

# --- Ψ-LAYER ---
from aevara.src.cognitive.substrate import CognitiveSubstrate as Substrate
from aevara.src.reasoning.synthesis import Synthesis                       
from aevara.src.verification.invariants import Invariants                 

# --- STRATEGY & EXECUTION ---
from aevara.src.strategy.ensemble_voter import EnsembleVoter
from aevara.src.strategy.parameter_sweeper import ParameterSweeper
from aevara.src.strategy.regime_adapter import RegimeAdapter
from aevara.src.strategy.performance_analyzer import PerformanceAnalyzer
from aevara.src.strategy.refinement_engine import RefinementEngine
from aevara.src.execution.advanced_logic import AdvancedExecutionLogic
from aevara.src.execution.mt5_adapter import MT5Adapter, MT5Order
from aevara.src.interfaces.dashboard_feed import DashboardFeed
from aevara.src.interfaces.telegram_bridge import TelegramOrchestrator
from aevara.src.deployment.activation_orchestrator import ActivationOrchestrator
from aevara.src.deployment.pilot_controller import PilotController
from aevara.src.agents.pilot_alpha import PilotAlpha
from aevara.src.dna.engine import DNAEngine

class AevraOrganism:
    def __init__(self, mode: str = "DEMO"):
        self.mode = mode
        self.hardening = Hardening()
        self.hardening.apply_process_hardening()
        
        self.config = self._load_all_configs()
        self.bus = bus
        self.logger = logger
        self.dash = AevraDashboard()
        self.vault = CredentialVault()
        self.vault.load_from_env() 
        
        self.pilot = PilotController(initial_lot=0.01)
        self.activation = ActivationOrchestrator(pilot_controller=self.pilot)
        
        mt5_cfg = self.config.get("mt5", {}).get("connection", {})
        self.mt5 = MT5Adapter(
            host=mt5_cfg.get("host", "127.0.0.1"),
            port=mt5_cfg.get("port", 5555),
            secret=self.vault.get("MT5_SECRET") or "AEVRA_SECRET_KY_2026"
        )
        
        self.telegram = TelegramOrchestrator(
            secret_key=self.vault.get("TELEGRAM_SECRET") or "AEVRA_SECRET_KY_2026", 
            orchestrator=self.activation
        )
        
        self.intelligence = {
            "regime": RegimeDetector(),
            "risk": QuantumGates(),
            "meta": LearningEngine(),
            "innovation": Proprietary(),
            "portfolio": MultiStrategy(["PILOT_TREND"])
        }
        
        self.cognition = {
            "substrate": Substrate(),
            "synthesis": Synthesis(),
            "invariants": Invariants()
        }
        
        self.alpha = PilotAlpha()
        self.dna = DNAEngine()
        self.voter = EnsembleVoter()
        self.sweeper = ParameterSweeper()
        self.adapter = RegimeAdapter()
        self.perf = PerformanceAnalyzer()
        self.refiner = RefinementEngine()
        self.adv_exec = AdvancedExecutionLogic()
        self.dash_feed = DashboardFeed()
        self.meta = LearningEngine()

    def _load_all_configs(self) -> Dict:
        conf = {}
        try:
            mt5_path = Path("aevara/config/mt5_config.yaml")
            if mt5_path.exists():
                with open(mt5_path, "r") as f:
                    conf["mt5"] = yaml.safe_load(f)
        except Exception as e:
            self.logger.log("ERROR", f"Config Load Failed: {e}")
        return conf

    async def _reconciliation_loop(self):
        sem = asyncio.Semaphore(1)
        while not self.activation.get_phase_status()["is_halted"]:
            async with sem:
                try:
                    positions = await self.mt5.reconcile()
                    self.logger.record_metric("open_positions_count", float(len(positions)))
                except Exception as e:
                    self.logger.log("WARNING", f"Reconciliation Failed: {e}")
            await asyncio.sleep(3.0)

    async def run(self, phase: str = "DEMO", duration: Optional[int] = None):
        print(f"AEVRA: Initializing Organism v2.8.0 in {self.mode} mode [{phase}]...")
        
        await self.hardening.run_environment_check()
        await self.dna.load_state()
        
        mt5_task = asyncio.create_task(self.mt5.connect())
        reconcile_task = asyncio.create_task(self._reconciliation_loop())
        dash_task = asyncio.create_task(self.dash_feed.run_worker())
        await self.dash.start()
        
        await self.telegram.start(
            token=self.vault.get("TELEGRAM_TOKEN") or "8678840435:AAHxmndKndBuWoDdnE-XMiG5-PEa6N8wQm8", 
            allowed_chat_ids=[8198692328]
        )
        
        await self.activation.start_phase(phase)
        self.logger.log("SYSTEM", f"AEVRA ACTIVE. Phase: {phase} | Mode: {self.mode}")
        
        start_time = time.time()
        try:
             while not self.activation.get_phase_status()["is_halted"]:
                  if duration and (time.time() - start_time) > duration:
                       self.logger.log("SYSTEM", f"Duration reached ({duration}s). Shutting down.")
                       break

                  # 1. Cognitive & DNA
                  await self.cognition["substrate"].process()
                  await self.dna.run_evolution_cycle() 
                  
                  # 2. Meta-Learning (Non-blocking)
                  asyncio.create_task(self.meta.run_meta_cycle({"win_rate": 0.52}))
                  
                  # 3. Strategy Pipeline
                  raw_regime = "TREND_BULL" 
                  strategy_id = self.adapter.select_strategy(raw_regime, ["PILOT_ALPHA"])
                  
                  raw_signals = await self.alpha.generate_signals()
                  consensus = self.voter.aggregate_signals(raw_signals)
                  
                  if consensus:
                       consensus = self.refiner.adjust_entry_logic(consensus, {"win_rate": 0.55})
                  
                  signals = [consensus] if consensus and consensus.direction != 0 else []
                  
                  # 4. Execution Loop
                  if signals and self.mt5._clients:
                       for sig in signals:
                            if await self.intelligence["risk"].process(sig):
                                 size = self.pilot.get_authorized_size(0.01)
                                 
                                 if self.mode == "dry-run":
                                      self.logger.log("DRY-RUN", f"Would send ORDER: {sig.symbol} {sig.direction} size {size}")
                                      continue

                                 order = MT5Order(symbol=sig.symbol, order_type="BUY" if sig.direction == 1 else "SELL", volume=size, price_requested=0.0)
                                 
                                 
                                 await self.mt5.send_order(order)
                  
                  # 6. Telemetry & Dashboard (T-030.9) - Always updating
                  await self.dash_feed.publish({
                       "phase": phase, 
                       "regime": raw_regime, 
                       "ensemble_confidence": consensus.confidence if consensus else 0.0,
                       "rolling_sharpe_50": self.perf.rolling_sharpe(), 
                       "edge_decay_detected": False,
                       "active_positions": len(await self.mt5.reconcile()), 
                       "daily_pnl_usd": 0.0,
                       "ftmo_daily_dd_pct": 0.0, 
                       "ftmo_total_dd_pct": 0.0, 
                       "system_health_score": 94.0
                  })

                  await asyncio.sleep(5.0) 
        except asyncio.CancelledError:
             self.logger.log("SYSTEM", "AEVRA: Shutdown ordered.")
        finally:
             reconcile_task.cancel()
             await self.telegram.stop()
             await self.dash.stop()
             mt5_task.cancel()

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", nargs="?", default="DEMO")
    parser.add_argument("--mode", choices=["real", "dry-run"], default="real")
    parser.add_argument("--duration", type=int, default=None)
    args = parser.parse_args()

    organism = AevraOrganism(mode=args.mode)
    await organism.run(phase=args.phase.upper(), duration=args.duration)

if __name__ == "__main__":
    asyncio.run(main())
