# @module: aevara.src.interfaces.dashboard_feed
# @deps: asyncio, json, os, datetime
# @status: IMPLEMENTED_v1.0
# @last_update: 2026-04-10
# @summary: Async dashboard feed publishing critical metrics to JSON for terminal viewer consumption (Ψ-9).

from __future__ import annotations
import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from aevara.src.telemetry.structured_logger import logger

class DashboardFeed:
    """
    Feed de Dashboard (Ψ-9).
    Publica métricas críticas em um buffer persistente (JSON) para consumo pelo viewer terminal.
    """
    def __init__(self, output_path: str = "aevara/state/dashboard.json"):
        self.output_path = output_path
        self._queue: asyncio.Queue = asyncio.Queue()
        self._is_running = False

    async def publish(self, metrics: Dict[str, Any]):
        """Adiciona métricas à fila de publicação asíncrona."""
        await self._queue.put(metrics)

    async def run_worker(self):
        """Worker que persiste a última métrica no disco de forma não-bloqueante."""
        self._is_running = True
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        
        while self._is_running:
            try:
                metrics = await self._queue.get()
                metrics["published_at"] = datetime.now().isoformat()
                
                # Escrita atômica para evitar corrupção de leitura pelo viewer
                temp_path = f"{self.output_path}.tmp"
                with open(temp_path, "w") as f:
                    json.dump(metrics, f, indent=2)
                
                os.replace(temp_path, self.output_path)
                self._queue.task_done()
            except Exception as e:
                logger.log("ERROR", f"DashboardFeed Worker Error: {e}")
                await asyncio.sleep(1.0)

    def stop(self):
        self._is_running = False
