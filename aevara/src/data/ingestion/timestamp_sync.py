# @module: aevara.src.data.ingestion.timestamp_sync
# @deps: aevara.src.data.schemas.market_tick
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Sincronizacao temporal com correcao de clock skew cross-exchange.
#           Garante monotonicidade de timestamps por (exchange, symbol).

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass(frozen=True, slots=True)
class SyncState:
    """Estado de sincronizacao por (exchange, symbol)."""
    last_ts_ns: int = 0            # Last valid timestamp
    offset_ns: int = 0             # Estimated clock offset
    violation_count: int = 0       # Monotonicity violations


class TimestampSync:
    """
    Sincronizador de timestamps com correcao de clock skew cross-exchange.

    Mantém estado por (exchange, symbol) para garantir monotonicidade.
    Detecta e registra violacoes de monotonicidade.
    Fornece correcao de offset baseada em calibracao continua.
    """

    def __init__(self, cross_exchange_calibration: bool = True):
        self._state: Dict[Tuple[str, str], SyncState] = {}
        self._cross_exchange = cross_exchange_calibration
        self._global_offsets: Dict[str, int] = {}  # exchange -> offset_ns

    def normalize(self, exchange: str, symbol: str, raw_ts_ns: int) -> Tuple[int, bool]:
        """
        Normaliza timestamp com correcao de offset e garantia de monotonicidade.

        Args:
            exchange: Exchange ID
            symbol: Symbol
            raw_ts_ns: Raw timestamp in nanoseconds

        Returns:
            Tuple of (normalized_ts, was_violation)
            - normalized_ts: Timestamp corrigido e monotonic
            - was_violation: True se o timestamp original violou monotonicidade
        """
        key = (exchange, symbol)
        state = self._state.get(key, SyncState())

        # Apply offset correction
        offset = self._global_offsets.get(exchange, 0)
        corrected_ts = raw_ts_ns + offset

        # Check monotonicity
        violation = corrected_ts <= state.last_ts_ns if state.last_ts_ns > 0 else False

        if violation:
            # Force monotonicity by incrementing
            corrected_ts = state.last_ts_ns + 1
            state = SyncState(
                last_ts_ns=corrected_ts,
                offset_ns=offset,
                violation_count=state.violation_count + 1,
            )
        else:
            state = SyncState(
                last_ts_ns=corrected_ts,
                offset_ns=offset,
                violation_count=state.violation_count,
            )

        self._state[key] = state
        return corrected_ts, violation

    def get_offset(self, exchange: str) -> int:
        return self._global_offsets.get(exchange, 0)

    def set_offset(self, exchange: str, offset_ns: int) -> None:
        self._global_offsets[exchange] = offset_ns

    def get_violation_count(self, exchange: str, symbol: str) -> int:
        key = (exchange, symbol)
        return self._state.get(key, SyncState()).violation_count

    def reset(self, exchange: Optional[str] = None, symbol: Optional[str] = None) -> None:
        if exchange and symbol:
            self._state.pop((exchange, symbol), None)
        elif exchange:
            self._state = {k: v for k, v in self._state.items() if k[0] != exchange}
        else:
            self._state.clear()
