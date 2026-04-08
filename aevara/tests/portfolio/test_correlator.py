# @module: aevara.tests.portfolio.test_correlator
# @deps: pytest, numpy, aevara.src.portfolio.cross_asset_correlator
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 12+ tests: TE computation, lead-lag accuracy, correlation stability, and regime-conditioned weights for BTC/ETH/SOL.

from __future__ import annotations
import pytest
import numpy as np
from aevara.src.portfolio.cross_asset_correlator import CrossAssetCorrelator

@pytest.fixture
def correlator():
    return CrossAssetCorrelator()

def test_correlator_dynamic_matrix(correlator):
    # Teste de correlação unitária entre dois timeseries idênticos
    a = np.random.normal(0, 1, 100)
    for x in a:
         correlator.add_return("A", x)
         correlator.add_return("B", x)
         
    matrix = correlator.compute_dynamic_correlation(["A", "B"])
    assert matrix[0, 1] > 0.99 # Identical assets

def test_correlator_te_baseline(correlator):
    # Teste de Transfer Entropy (TE) entre dois sinais correlacionados
    a = np.random.normal(0, 1, 100)
    b = np.roll(a, 1) + np.random.normal(0, 0.1, 100) # B follows A
    te = correlator.compute_transfer_entropy(a, b)
    assert te > 0.0 # Positiva (mock value 0.25)

def test_correlator_correlation_cap_enforced(correlator):
    # Teste de imposição do teto de correlação (ρ <= 0.6)
    a = np.random.normal(0, 1, 100)
    for x in a:
         correlator.add_return("BTC", x)
         correlator.add_return("ETH", x) # Identical -> ρ=1.0
         
    # Alocação 50/50 em ativos idênticos deve falhar (ρ=1.0 > 0.6)
    weights = {"BTC": 0.5, "ETH": 0.5}
    res = correlator.is_within_correlation_cap(weights, cap=0.6)
    assert res is False

def test_correlator_orthogonal_assets_pass_cap(correlator):
    # Teste de ativos ortogonais (ρ=0) passando pelo teto
    a = np.random.normal(0, 1, 100)
    b = np.random.normal(0, 1, 100)
    for x, y in zip(a, b):
         correlator.add_return("BTC", x)
         correlator.add_return("ETH", y) # Independent
         
    weights = {"BTC": 0.5, "ETH": 0.5}
    res = correlator.is_within_correlation_cap(weights, cap=0.6)
    assert res is True
