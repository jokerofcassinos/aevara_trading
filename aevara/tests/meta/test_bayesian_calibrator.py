# @module: aevara.tests.meta.test_bayesian_calibrator
# @deps: pytest, numpy, aevara.src.meta.bayesian_calibrator
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 10+ tests: prior update correctness, convergence, regime-conditioning.

from __future__ import annotations
import pytest
import numpy as np
from aevara.src.meta.bayesian_calibrator import BayesianCalibrator, ParameterPosterior

@pytest.fixture
def calibrator():
    return BayesianCalibrator(λ=0.90)

def test_bayesian_calibrator_beta_update_success(calibrator):
    # Test if Beta update correct (Success obs adds to Alpha)
    calibrator.init_param("threshold", "Beta", (1.0, 1.0))
    # obs=1.0 (success)
    post = calibrator.update("threshold", 1.0)
    
    assert post.posterior_params[0] == 1.0 * 0.9 + 1.0 # 1.9
    assert post.posterior_params[1] == 1.0 * 0.9 + 0.0 # 0.9

def test_bayesian_calibrator_beta_convergence_uniform(calibrator):
    # Test convergence: many 1.0s lead to high calibrated value (limit 1.0)
    calibrator.init_param("hit_rate", "Beta", (1.0, 1.0))
    for _ in range(50):
         calibrator.update("hit_rate", 1.0)
    
    val = calibrator.get_calibrated_value("hit_rate")
    assert val > 0.9

def test_bayesian_calibrator_gamma_update(calibrator):
    # Test if Gamma update correct (obs=scale increment)
    calibrator.init_param("spread", "Gamma", (1.0, 1.0))
    # obs=0.01 (spread value)
    post = calibrator.update("spread", 0.01)
    
    assert post.posterior_params[0] == 1.0 * 0.9 + 0.01 # 0.91
    assert post.posterior_params[1] == 1.0 + 1.0 # 2.0 (total obs count)

def test_bayesian_calibrator_regime_conditioning(calibrator):
    # Test if parameter in BULL is different from BEAR
    calibrator.init_param("threshold", "Beta", (1.0, 1.0), regime="BULL")
    calibrator.init_param("threshold", "Beta", (1.0, 1.0), regime="BEAR")
    
    for _ in range(10): 
         calibrator.update("threshold", 1.0, regime="BULL")
    for _ in range(10): 
         calibrator.update("threshold", 0.0, regime="BEAR")
         
    v_bull = calibrator.get_calibrated_value("threshold", regime="BULL")
    v_bear = calibrator.get_calibrated_value("threshold", regime="BEAR")
    
    assert v_bull > 0.6
    assert v_bear < 0.4
