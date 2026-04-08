import asyncio
from aevara.src.strategy.ensemble_voter import EnsembleVoter
from aevara.src.strategy.regime_adapter import RegimeAdapter
from aevara.src.strategy.parameter_sweeper import ParameterSweeper

class MockSignal:
    def __init__(self, symbol, side, confidence, strategy_id):
        self.symbol = symbol
        self.side = side
        self.confidence = confidence
        self.strategy_id = strategy_id

async def test_strategic_pipeline():
    voter = EnsembleVoter()
    adapter = RegimeAdapter()
    sweeper = ParameterSweeper(budget=10)
    
    # 1. Test Ensemble Conflit
    signals = [
        MockSignal("BTCUSD", "BUY", 0.8, "STRAT_A"),
        MockSignal("BTCUSD", "SELL", 0.6, "STRAT_B")
    ]
    consensus = voter.aggregate_signals(signals)
    print(f"Consensus Confidence (Conflict): {consensus.confidence:.2f}")
    assert consensus.confidence < 0.5 # Confidence should be low due to conflict
    
    # 2. Test Regime Adaptation
    strategy = adapter.select_strategy("TREND_BULL", ["TREND_FOLLOWING", "SCALPING"])
    assert strategy == "TREND_FOLLOWING"
    
    # 3. Test Sweeper
    def objective(p): return -(p['x']-2)**2
    best = await sweeper.online_optimize(objective, {'x': (0, 4)}, timeout=5.0)
    print(f"Optimal X: {best['x']:.2f}")
    assert 1.5 < best['x'] < 2.5
    
    print("✅ Strategic Pipeline Test: PASS")

if __name__ == "__main__":
    asyncio.run(test_strategic_pipeline())
