# @module: aevara.tests.unit.risk.test_quantum_gates
# @deps: aevara.src.risk.quantum_gates, numpy
# @status: TEST_PILOT
# @summary: Validation of Empirical CVaR and Fractional Kelly math (T-030.2.2).

import pytest
import numpy as np
from aevara.src.risk.quantum_gates import QuantumGates

class MockSignal:
    def __init__(self, edge, confidence):
        self.edge = edge
        self.confidence = confidence

def test_cvar_math():
    qg = QuantumGates()
    # Pior cenário: perdas de 10% constantes
    returns = np.array([-0.1] * 100)
    cvar = qg.calculate_cvar(returns)
    assert cvar == 0.1 # Média do pior quantil de -0.1 (absoluto)

def test_kelly_bounds():
    qg = QuantumGates(risk_aversion=1.0) # Full Kelly for testing
    # Edge alto, risk baixo
    size = qg.fractional_kelly(edge=0.1, win_rate=0.6, cvar=0.01)
    assert size == 0.05 # Clamped at Max (5%)
    
    # Edge zero
    size = qg.fractional_kelly(edge=0.0, win_rate=0.5, cvar=0.01)
    assert size == 0.001 # Clamped at Min (0.1%)

@pytest.mark.asyncio
async def test_gate_rejection():
    qg = QuantumGates(risk_aversion=0.25)
    # Sinal com edge irrelevante frente ao CVaR
    bad_signal = MockSignal(edge=0.0001, confidence=0.5)
    passed = await qg.process(bad_signal)
    assert passed == False

@pytest.mark.asyncio
async def test_gate_approval():
    qg = QuantumGates(risk_aversion=0.25)
    # Sinal com edge forte (2% edge vs 1% tail risk)
    good_signal = MockSignal(edge=0.02, confidence=0.9)
    # Nota: process() usa retornos aleatórios no mock interno, 
    # mas estatisticamente deve passar na maioria das vezes.
    # Como o mock interno usa normal(0.0001, 0.01), o CVaR(95%) sera aprox 0.02
    # 0.02 / 0.02 = 1.0 > 0.1.
    passed = await qg.process(good_signal)
    assert passed == True
