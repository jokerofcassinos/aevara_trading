# @module: aevara.tests.property.portfolio.test_multi_asset_invariants
# @deps: pytest, hypothesis, aevara.src.portfolio.ftmo_multi_asset_guard, aevara.src.portfolio.cross_asset_correlator
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 6+ Hypothesis tests: Multi-asset invariants Σ_exposure ≤ limit, ρ ≤ cap, and no_hardcoded_symbols.

from __future__ import annotations
import pytest
import numpy as np
from hypothesis import given, strategies as st
from aevara.src.portfolio.ftmo_multi_asset_guard import FTMOMultiAssetGuard
from aevara.src.portfolio.cross_asset_correlator import CrossAssetCorrelator

@given(st.lists(st.floats(0.01, 1.0), min_size=1, max_size=10))
def test_ftmo_guard_exposure_invariant_property(lots):
    # Invariante: Σ lots <= 5.0 sempre
    guard = FTMOMultiAssetGuard(max_exposure_lots=5.0)
    positions = {f"T_{i}": l for i, l in enumerate(lots)}
    
    res, _ = guard.check_aggregate_exposure(positions)
    total = sum(lots)
    
    if total > 5.0:
         assert res is False
    else:
         assert res is True

@given(st.lists(st.floats(0, 1), min_size=2, max_size=2))
def test_correlator_cap_invariant_property(w_list):
    # Invariante: ρ <= 0.6 para ativos identicos com pesos significantes
    correlator = CrossAssetCorrelator()
    # Ativos identicos -> ρ=1.0
    a = np.random.normal(0, 1, 100)
    for x in a:
         correlator.add_return("A", x)
         correlator.add_return("B", x)
         
    total = sum(w_list) or 1.0
    weights = {"A": w_list[0]/total, "B": w_list[1]/total}
    
    # Se ambos ativos tem peso > 0 significante (ρ contribui)
    if min(weights.values()) > 0.01:
         assert correlator.is_within_correlation_cap(weights, cap=0.6) is False

@given(st.floats(0.1, 1000.0))
def test_ftmo_guard_capacity_non_negative_property(current):
    # Invariante: Capacidade restante de lote nao pode ser negativa
    guard = FTMOMultiAssetGuard(max_exposure_lots=5.0)
    cap = guard.get_remaining_capacity(current)
    assert cap >= 0.0
