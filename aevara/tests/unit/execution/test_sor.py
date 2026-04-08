# @module: aevara.tests.unit.execution.test_sor
# @deps: aevara.src.execution.sor
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para SmartOrderRouter: venue selection, TCE gating,
#           fee optimization, fallback chain, split planning.

from __future__ import annotations

import pytest

from aevara.src.execution.sor import (
    SmartOrderRouter,
    SORDecision,
    VenueInfo,
)


def make_venue(
    venue_id: str,
    taker_fee: float = 10.0,
    maker_fee: float = 2.0,
    latency: int = 500,
    fill_rate: float = 0.95,
    slippage: float = 3.0,
    available: bool = True,
    min_size: float = 0.001,
    max_size: float = 100.0,
) -> VenueInfo:
    return VenueInfo(
        venue_id=venue_id,
        taker_fee_bps=taker_fee,
        maker_fee_bps=maker_fee,
        avg_latency_us=latency,
        fill_rate=fill_rate,
        avg_slippage_bps=slippage,
        available=available,
        min_order_size=min_size,
        max_order_size=max_size,
    )


def make_router() -> SmartOrderRouter:
    venues = {
        "binance": make_venue(
            "binance", taker_fee=10.0, maker_fee=0.0, latency=300,
            fill_rate=0.98, slippage=2.0, max_size=100.0,
        ),
        "coinbase": make_venue(
            "coinbase", taker_fee=10.0, maker_fee=5.0, latency=800,
            fill_rate=0.92, slippage=4.0, max_size=50.0,
        ),
        "kraken": make_venue(
            "kraken", taker_fee=16.0, maker_fee=10.0, latency=1200,
            fill_rate=0.89, slippage=5.0, max_size=30.0,
        ),
    }
    return SmartOrderRouter(venues)


# === ROUTING ===
class TestVenueRouting:
    def test_selects_lowest_tce_venue(self):
        router = make_router()
        decision = router.route(
            symbol="BTC/USD",
            side="BUY",
            size=1.0,
            order_type="LIMIT",
            tce_budget_bps=20.0,
            is_maker=True,
        )
        assert decision is not None
        # Binance maker fee is 0, so it should be selected
        assert decision.selected_venue == "binance"

    def test_taker_routing(self):
        router = make_router()
        decision = router.route(
            symbol="BTC/USD",
            side="BUY",
            size=1.0,
            order_type="MARKET",
            tce_budget_bps=20.0,
            is_maker=False,
        )
        assert decision is not None
        # All taker fees are 10, but binance has lower slippage
        assert decision.selected_venue == "binance"

    def test_no_venues_available(self):
        router = SmartOrderRouter()
        decision = router.route(
            symbol="BTC/USD", side="BUY", size=1.0,
            order_type="LIMIT", tce_budget_bps=20.0,
        )
        assert decision is None

    def test_respects_budget(self):
        router = SmartOrderRouter({
            "expensive": make_venue(
                "expensive", taker_fee=50.0, maker_fee=40.0,
                slippage=20.0,
            )
        })
        decision = router.route(
            symbol="BTC/USD", side="BUY", size=1.0,
            order_type="LIMIT", tce_budget_bps=10.0,
        )
        # TCE = 50 + 20 = 70 > 10 budget
        assert decision is None

    def test_accepts_when_within_budget(self):
        router = SmartOrderRouter({
            "cheap": make_venue(
                "cheap", taker_fee=5.0, maker_fee=2.0, slippage=1.0,
            )
        })
        decision = router.route(
            symbol="BTC/USD", side="BUY", size=1.0,
            order_type="LIMIT", tce_budget_bps=20.0,
        )
        assert decision is not None
        assert decision.selected_venue == "cheap"
        assert decision.expected_tce_bps <= 20.0


# === TCE COMPUTATION ===
class TestTCEComputation:
    def test_tce_maker_vs_taker(self):
        venue = make_venue("test", taker_fee=10.0, maker_fee=2.0, slippage=3.0)
        router = SmartOrderRouter()
        tce_taker = router.compute_tce(venue, is_maker=False)
        tce_maker = router.compute_tce(venue, is_maker=True)
        assert tce_maker < tce_taker

    def test_tce_with_impact(self):
        venue = make_venue("test", taker_fee=10.0, slippage=3.0)
        router = SmartOrderRouter()
        tce_base = router.compute_tce(venue)
        tce_impact = router.compute_tce(venue, market_impact_bps=5.0)
        assert tce_impact > tce_base

    def test_tce_with_funding(self):
        venue = make_venue("test", taker_fee=10.0, slippage=3.0)
        router = SmartOrderRouter()
        tce_no_funding = router.compute_tce(venue, funding_bps=0.0)
        tce_funding = router.compute_tce(venue, funding_bps=2.0)
        assert tce_funding == tce_no_funding + 2.0


# === FALLBACK CHAIN ===
class TestFallbackChain:
    def test_returns_alternatives(self):
        router = make_router()
        fallbacks = router.get_fallback_chain("binance")
        assert "coinbase" in fallbacks and "kraken" in fallbacks
        assert "binance" not in fallbacks
        # Should be ordered by TCE (ascending)
        assert len(fallbacks) == 2

    def test_empty_for_unknown_venue(self):
        router = SmartOrderRouter()
        fallbacks = router.get_fallback_chain("nonexistent")
        assert fallbacks == []


# === ALGORITHM SELECTION ===
class TestAlgoSelection:
    def test_twap_for_large_orders(self):
        router = make_router()
        decision = router.route(
            symbol="BTC/USD", side="BUY", size=80.0,  # 80% of max_size
            order_type="LIMIT", tce_budget_bps=20.0,
        )
        assert decision is not None
        assert decision.algo == "TWAP"

    def test_smart_limit_for_ioc(self):
        router = make_router()
        decision = router.route(
            symbol="BTC/USD", side="BUY", size=1.0,
            order_type="IOC", tce_budget_bps=20.0,
        )
        assert decision is not None
        assert decision.algo == "SMART_LIMIT"

    def test_pov_for_market_order(self):
        router = make_router()
        decision = router.route(
            symbol="BTC/USD", side="BUY", size=1.0,
            order_type="MARKET", tce_budget_bps=20.0,
        )
        assert decision is not None
        assert decision.algo == "POV"

    def test_split_plan_for_twap(self):
        router = make_router()
        decision = router.route(
            symbol="BTC/USD", side="BUY", size=80.0,
            order_type="LIMIT", tce_budget_bps=20.0,
        )
        assert decision is not None
        assert decision.split_plan == pytest.approx([sum(decision.split_plan) / len(decision.split_plan)] * len(decision.split_plan))
        assert abs(sum(decision.split_plan) - 1.0) < 0.01

    def test_single_slice_for_smart_limit(self):
        router = make_router()
        decision = router.route(
            symbol="BTC/USD", side="BUY", size=1.0,
            order_type="LIMIT", tce_budget_bps=20.0,
        )
        assert decision is not None
        assert decision.split_plan == [1.0]


# === VENUE MANAGEMENT ===
class TestVenueManagement:
    def test_add_venue(self):
        router = SmartOrderRouter()
        router.add_venue("test", make_venue("test"))
        assert "test" in router.get_available_venues()

    def test_remove_venue(self):
        router = make_router()
        assert router.remove_venue("binance")
        assert "binance" not in router.get_available_venues()

    def test_remove_nonexistent(self):
        router = SmartOrderRouter()
        assert not router.remove_venue("nonexistent")

    def test_get_venue_info(self):
        router = make_router()
        info = router.get_venue_info("binance")
        assert info is not None
        assert info.venue_id == "binance"

    def test_unavailable_venue_excluded(self):
        router = make_router()
        router.add_venue("down", make_venue("down", available=False))
        assert "down" not in router.get_available_venues()

    def test_update_venue_latency(self):
        router = make_router()
        assert router.get_venue_info("binance").avg_latency_us == 300
        router.update_venue_latency("binance", 1000)
        assert router.get_venue_info("binance").avg_latency_us == 1000
