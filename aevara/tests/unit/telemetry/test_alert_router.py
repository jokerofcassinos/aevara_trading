# @module: aevara.tests.unit.telemetry.test_alert_router
# @deps: aevara.src.telemetry.alert_router
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para AlertRouter: routing by level, dedup, escalation,
#           suppression, history bounded.

from __future__ import annotations

import time
import pytest

from aevara.src.telemetry.alert_router import (
    Alert, AlertAction, AlertLevel, AlertRouter,
)


def make_alert(level: AlertLevel = AlertLevel.WARNING, dedup_key: str = "k1", message: str = "Alert") -> Alert:
    return Alert(
        level=level,
        component="test",
        message=message,
        metric_name="metric_x",
        metric_value=1.0,
        threshold=0.5,
        dedup_key=dedup_key,
        timestamp_ns=time.time_ns(),
    )


# === HAPPY PATH ===
class TestAlertRouterHappyPath:
    def test_info_routes_to_log(self):
        router = AlertRouter()
        action = router.route(make_alert(AlertLevel.INFO))
        assert action.routed
        assert action.channel == "log"

    def test_warning_routes_to_log(self):
        router = AlertRouter()
        action = router.route(make_alert(AlertLevel.WARNING))
        assert action.routed
        assert action.channel == "log"

    def test_critical_routes_to_telegram(self):
        router = AlertRouter()
        action = router.route(make_alert(AlertLevel.CRITICAL))
        assert action.routed
        assert action.channel == "telegram"

    def test_fatal_routes_to_all(self):
        router = AlertRouter()
        action = router.route(make_alert(AlertLevel.FATAL))
        assert action.routed
        assert action.channel == "all"

    def test_history_tracks_alerts(self):
        router = AlertRouter()
        for i in range(5):
            router.route(make_alert(dedup_key=f"k_{i}"))
        assert router.alert_count == 5


# === DEDUPLICATION ===
class TestAlertRouterDedup:
    def test_duplicate_suppressed_within_window(self):
        router = AlertRouter(dedup_window_s=300.0)
        ts = time.time_ns()
        a1 = Alert(
            level=AlertLevel.WARNING, component="test", message="Alert",
            metric_name="m", metric_value=1.0, threshold=0.5,
            dedup_key="dup_key", timestamp_ns=ts,
        )
        a2 = Alert(
            level=AlertLevel.WARNING, component="test", message="Alert",
            metric_name="m", metric_value=1.0, threshold=0.5,
            dedup_key="dup_key", timestamp_ns=ts + 1_000_000,  # 1ms later
        )
        r1 = router.route(a1)
        r2 = router.route(a2)
        assert r1.routed
        assert not r2.routed
        assert "Dedup" in r2.suppress_reason

    def test_different_dedup_key_not_suppressed(self):
        router = AlertRouter(dedup_window_s=300.0)
        a1 = make_alert(dedup_key="k1")
        a2 = make_alert(dedup_key="k2")
        r1 = router.route(a1)
        r2 = router.route(a2)
        assert r1.routed
        assert r2.routed


# === EDGE CASES ===
class TestAlertRouterEdgeCases:
    def test_history_is_bounded(self):
        router = AlertRouter(max_alert_history=100)
        for i in range(200):
            router.route(make_alert(dedup_key=f"k_{i}"))
        assert router.alert_count <= 100

    def test_get_recent_alerts(self):
        router = AlertRouter()
        for i in range(10):
            router.route(make_alert(dedup_key=f"k_{i}"))
        recent = router.get_recent_alerts(5)
        assert len(recent) == 5

    def test_suppressed_count(self):
        router = AlertRouter(dedup_window_s=300.0)
        ts = time.time_ns()
        router.route(Alert(
            level=AlertLevel.WARNING, component="test", message="Alert",
            metric_name="m", metric_value=1.0, threshold=0.5,
            dedup_key="same", timestamp_ns=ts,
        ))
        router.route(Alert(
            level=AlertLevel.WARNING, component="test", message="Alert",
            metric_name="m", metric_value=1.0, threshold=0.5,
            dedup_key="same", timestamp_ns=ts + 1000,
        ))
        suppressed = router.get_suppressed_count()
        assert suppressed >= 1

    def test_reset_clears_history(self):
        router = AlertRouter()
        for i in range(10):
            router.route(make_alert(dedup_key=f"k_{i}"))
        router.reset()
        assert router.alert_count == 0
        assert router.get_suppressed_count() == 0
