# @module: aevara.src.interfaces.dashboard
# @deps: asyncio, rich, telemetry.structured_logger
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Async Terminal Dashboard (v1.0.0) for real-time organism monitoring (Ω-10).

from __future__ import annotations
import asyncio
import time
from typing import Dict, Any, List

try:
    from rich.live import Live
    from rich.table import Table
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.console import Console
    from rich.progress import Progress, BarColumn, TextColumn
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from aevara.src.telemetry.structured_logger import logger

class AevraDashboard:
    """
    AEVRA Execution Dashboard (v1.0.0).
    Mostra métricas de regime, alocação e saúde do sistema em tempo real.
    """
    def __init__(self):
        self.console = Console() if RICH_AVAILABLE else None
        self._is_running = False

    def _create_layout(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )
        return layout

    def _generate_table(self, metrics: Dict[str, float]) -> Table:
        table = Table(title="Ω-Layer Metrics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta")
        for k, v in metrics.items():
            table.add_row(k, f"{v:.4f}")
        return table

    async def update_loop(self):
        """Loop principal de renderização do dashboard."""
        if not RICH_AVAILABLE:
            print("DASHBOARD: Rich not available. Falling back to simple logging.")
            return

        with Live(self._create_layout(), refresh_per_second=2, screen=True) as live:
            while True:
                metrics = logger.get_latest_metrics()
                events = logger.get_event_stream(10)
                
                # Header
                header_panel = Panel("AEVRA — QUANTUM TRADING ORGANISM (v1.0.0-rc) | Phase: DEMO", style="bold green")
                
                # Main Views
                metrics_table = self._generate_table(metrics)
                
                event_log = Table(title="System Event Log", box=None)
                event_log.add_column("TS", style="dim")
                event_log.add_column("Msg", style="white")
                for e in events:
                    ts = time.strftime("%H:%M:%S", time.localtime(e["ts_ns"]/1e9))
                    event_log.add_row(ts, e["msg"])

                layout = self._create_layout()
                layout["header"].update(header_panel)
                layout["left"].update(Panel(metrics_table, title="Intelligence Surface"))
                layout["right"].update(Panel(event_log, title="Neural Activity"))
                layout["footer"].update(Panel(f"Last Update: {time.ctime()} | Pilot Lock: 0.01 Lots", style="dim"))

                live.update(layout)
                await asyncio.sleep(0.5)

    async def start(self):
        self._is_running = True
        asyncio.create_task(self.update_loop())

    async def stop(self):
        self._is_running = False
