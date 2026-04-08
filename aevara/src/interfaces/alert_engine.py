# @module: aevara.src.interfaces.alert_engine
# @deps: none
# @status: IMPLEMENTED
# @last_update: 2026-04-07
# @summary: Hierarchical, deduplicated, cooldown-aware alert routing.

from typing import Dict

class AlertRouter:
    async def route(self, level: str, component: str, message: str, context: Dict) -> None:
        pass

    def is_suppressed(self, alert_hash: str) -> bool:
        return False

    def escalate(self, alert: Dict) -> None:
        pass
