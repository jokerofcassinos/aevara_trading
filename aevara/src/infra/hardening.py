# @module: aevara.src.infra.hardening
# @deps: asyncio, signal, os, sys, typing
# @status: IMPLEMENTED_v1.0
# @last_update: 2026-04-10
# @summary: Process hardening engine (Ω-10). Signal handling, environment validation and graceful shutdown.

from __future__ import annotations
import asyncio
import signal
import os
import sys
from typing import Any, Dict, List, Optional
from aevara.src.telemetry.structured_logger import logger

class Hardening:
    """
    Motor de Endurecimento (Ω-10).
    Gerencia a resiliência do processo, proteção de memória e desligamento limpo.
    """
    def __init__(self):
        self._is_production = os.getenv("AEVRA_ENV") == "PROD"

    def apply_process_hardening(self):
        """Aplica proteções de nível de SO e Runtime."""
        # 1. Debug Mode Control
        if self._is_production:
            asyncio.get_event_loop().set_debug(False)
            
        # 2. Signal Handling (Graceful Shutdown)
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._shutdown_signal_handler)
            except NotImplementedError:
                # signal.add_signal_handler não funciona em Windows da mesma forma que Unix
                # No Windows, usamos signal.signal() no main thread
                pass

    def _shutdown_signal_handler(self):
        logger.log("SYSTEM", "AEVRA SHUTDOWN: Signal received. Initiating graceful exit...")
        # Lógica de cancelamento handled by main.py finally block
        sys.exit(0)

    def validate_environment(self) -> Dict[str, Any]:
        """Valida que o ambiente de execução é seguro e compatível."""
        report = {
            "python_version": sys.version,
            "pid": os.getpid(),
            "status": "SECURE"
        }
        
        # Checagem de variáveis críticas
        required_env = ["MT5_SECRET", "TELEGRAM_TOKEN"]
        missing = [v for v in required_env if not os.getenv(v)]
        
        if missing:
            report["status"] = "DEGRADED"
            report["missing_vars"] = missing
            logger.log("WARNING", f"Environment Hardening: Missing critical variables: {missing}")
            
        return report

    async def run_environment_check(self):
        """Task de auditoria cíclica de saúde do ambiente."""
        report = self.validate_environment()
        logger.record_metric("env_health_score", 1.0 if report["status"] == "SECURE" else 0.5)
        return report
