# @module: aevara.src.dna.engine
# @deps: typing, asyncio, telemetry.logger, dna.shadow_weights, dna.promotion_gate
# @status: IMPLEMENTED_v1.0
# @last_update: 2026-04-10
# @summary: DNA Orchestration Engine managing non-blocking evolution, promotion, and persistence (Ψ-0).

from __future__ import annotations
import asyncio
import os
from typing import Any, Dict, List, Optional
from aevara.src.telemetry.structured_logger import logger
from aevara.src.dna.shadow_weights import ShadowWeightManager, GradientBatch
from aevara.src.dna.promotion_gate import PromotionGate, GateAction

class DNAEngine:
    """
    Maestro de Evolução (Ψ-0).
    Orquestra o ciclo de adaptação de pesos, avaliação de promoção e persistência atômica.
    """
    def __init__(self, state_dir: str = "aevara/state"):
        self.state_dir = state_dir
        self.weights = ShadowWeightManager()
        self.gate = PromotionGate()
        self._is_frozen = False

    async def load_state(self):
        """Carrega estado persistente do DNA e Gate na inicialização."""
        w_path = os.path.join(self.state_dir, "dna_weights.json")
        g_path = os.path.join(self.state_dir, "promotion_gate.json")
        
        if self.weights.load(w_path):
            logger.log("DNA", "DNA weights loaded from checkpoint.")
        else:
            logger.log("DNA", "No DNA weights checkpoint found. Starting with priors.")
            
        if self.gate.load(g_path):
            logger.log("DNA", "Promotion gate state loaded from checkpoint.")

    async def run_evolution_cycle(self, gradients: Optional[GradientBatch] = None):
        """
        Executa um passo de evolução assíncrona.
        1. Atualiza Shadow Weights
        2. Avalia Promoção (Gate)
        3. Persiste Estado
        """
        if self._is_frozen or not gradients:
            return

        # 1. Update Shadow Weights (EMA + LR)
        updates = self.weights.apply_gradient(gradients)
        
        # 2. Record metrics in Gate
        self.gate.record(gradients.alignment_score, gradients.phantom_rr)
        
        # 3. Evaluate Promotion
        eval_result = self.gate.evaluate()
        
        if eval_result.action == GateAction.PROMOTE:
            logger.log("DNA", f"PROMOTION APPROVED: gen {self.weights.generation} -> {self.weights.generation + 1}")
            self.weights.atomic_swap()
            # Emit telemetry: dna_evolution_step
            logger.record_metric("dna_promoted", 1.0)
            
        # 4. Deep Persistent Save (Non-blocking)
        await asyncio.to_thread(self._persist_all)

    def _persist_all(self):
        """Executa gravação física no disco."""
        w_path = os.path.join(self.state_dir, "dna_weights.json")
        g_path = os.path.join(self.state_dir, "promotion_gate.json")
        self.weights.save(w_path)
        self.gate.save(g_path)

    def emergency_freeze(self):
        """Trava a evolução para diagnóstico."""
        self._is_frozen = True
        logger.log("DNA", "DNA EVOLUTION FROZEN.")

    def resume(self):
        self._is_frozen = False
        logger.log("DNA", "DNA EVOLUTION RESUMED.")
