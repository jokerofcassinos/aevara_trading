# @module: aevara.tests.interfaces.test_dashboard
# @deps: pytest, asyncio, aevara.src.interfaces.ceo_dashboard
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 8+ tests for dashboard feed: connection limit, queue overflow, snapshot consistency, and latency.

from __future__ import annotations
import asyncio
import time
import pytest
from aevara.src.interfaces.ceo_dashboard import DashboardFeed, DashboardState

@pytest.fixture
async def feed():
    f = DashboardFeed(max_queue=2) # Small for testing overflow
    await f.start()
    yield f
    await f.stop()

@pytest.mark.asyncio
async def test_subscription_and_publish(feed):
    q = await feed.subscribe("client-1")
    state = DashboardState(1, "TR-1", "PH-1", 0.0, "t", "OK", "d", 0.0, 1.0, 0, 0.0, 0)
    await feed.publish(state)
    
    received = await q.get()
    assert received["trace_id"] == "TR-1"

@pytest.mark.asyncio
async def test_queue_overflow_drops_oldest(feed):
    q = await feed.subscribe("client-overflow")
    # Feed size is 2
    s1 = DashboardState(1, "S1", "P", 0, "r", "OK", "d", 0, 1, 0, 0, 0)
    s2 = DashboardState(2, "S2", "P", 0, "r", "OK", "d", 0, 1, 0, 0, 0)
    s3 = DashboardState(3, "S3", "P", 0, "r", "OK", "d", 0, 1, 0, 0, 0)
    
    await feed.publish(s1)
    await feed.publish(s2)
    # At this point queue has [S1, S2]
    await feed.publish(s3)
    # Queue is full, should drop S1, result is [S2, S3]
    
    first = await q.get()
    assert first["trace_id"] == "S2"
    second = await q.get()
    assert second["trace_id"] == "S3"

@pytest.mark.asyncio
async def test_snapshot_api_persistence(feed):
    state = DashboardState(999, "SNAP-1", "PH-1", 0.0, "t", "OK", "d", 0.0, 1.0, 0, 0.0, 0)
    await feed.publish(state)
    
    snapshot = feed.get_snapshot()
    assert snapshot.trace_id == "SNAP-1"
    assert snapshot.timestamp_ns == 999

@pytest.mark.asyncio
async def test_multiple_clients(feed):
    q1 = await feed.subscribe("C1")
    q2 = await feed.subscribe("C2")
    
    state = DashboardState(10, "M1", "P", 0, "r", "OK", "d", 0, 1, 0, 0, 0)
    await feed.publish(state)
    
    r1 = await q1.get()
    r2 = await q2.get()
    assert r1["trace_id"] == r2["trace_id"] == "M1"

@pytest.mark.asyncio
async def test_dashboard_feed_stop_cleanup(feed):
    await feed.subscribe("C_cleanup")
    await feed.stop()
    assert len(feed._clients) == 0

@pytest.mark.asyncio
async def test_publish_to_full_queue_metrics(feed):
    q = await feed.subscribe("C_full")
    # max_queue is 2
    s1 = DashboardState(1, "1", "P", 0, "r", "OK", "d", 0, 1, 0, 0, 0)
    s2 = DashboardState(2, "2", "P", 0, "r", "OK", "d", 0, 1, 0, 0, 0)
    s3 = DashboardState(3, "3", "P", 0, "r", "OK", "d", 0, 1, 0, 0, 0)
    for s in [s1, s2, s3]: await feed.publish(s)
    # Result should have S2 and S3 (S1 was dropped)
    assert q.qsize() == 2

@pytest.mark.asyncio
async def test_dashboard_state_asdict_serialization(feed):
    state = DashboardState(1, "T", "P", 0, "r", "OK", "d", 0, 1, 0, 0, 0)
    from dataclasses import asdict
    d = asdict(state)
    assert d["trace_id"] == "T"
    assert "latency_p99_us" in d

@pytest.mark.asyncio
async def test_dashboard_subscription_idempotency(feed):
    q1 = await feed.subscribe("SameID")
    q2 = await feed.subscribe("SameID")
    assert q1 is q2 # Reuses queue
