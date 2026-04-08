# @module: aevara.src.data.features.normalizers
# @deps: aevara.src.utils.math
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Normalizacao de features: mid-price, spread_bps, imbalance_ratio,
#           e conversao para espaco log-odds.

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from aevara.src.utils.math import clip, logit, safe_div, sigmoid


@dataclass(frozen=True, slots=True)
class NormalizedFeatures:
    """Features normalizadas derivadas de um tick."""
    mid_price: float           # (bid + ask) / 2
    spread_bps: float          # (ask - bid) / mid_price * 10000
    imbalance_ratio: float     # (bid_vol - ask_vol) / (bid_vol + ask_vol) in [-1, 1]
    mid_price_logodds: float   # log-odds do mid_price normalizado
    spread_logodds: float      # log-odds do spread normalizado


def normalize_tick(bid: float, ask: float, bid_vol: float, ask_vol: float, ref_price: float = 1.0) -> NormalizedFeatures:
    """
    Normaliza features de um tick para espaco estandar.

    Args:
        bid: Best bid price
        ask: Best ask price
        bid_vol: Volume at best bid
        ask_vol: Volume at best ask
        ref_price: Reference price for normalization (e.g., previous mid)

    Returns:
        NormalizedFeatures com todas as features calculadas
    """
    mid_price = (bid + ask) / 2.0
    spread_bps = safe_div((ask - bid) * 10000, mid_price)

    total_vol = bid_vol + ask_vol
    imbalance_ratio = safe_div(bid_vol - ask_vol, total_vol)
    imbalance_ratio = clip(imbalance_ratio, -1.0, 1.0)

    # Convert to log-odds space for coherence fusion
    price_ratio = safe_div(mid_price, ref_price, 1.0)
    price_ratio_norm = clip(price_ratio / (1.0 + price_ratio), 1e-8, 1.0 - 1e-8)
    mid_price_logodds = logit(price_ratio_norm)

    spread_norm = clip(spread_bps / 1000.0, 1e-8, 1.0 - 1e-8)
    spread_logodds = logit(spread_norm)

    return NormalizedFeatures(
        mid_price=mid_price,
        spread_bps=spread_bps,
        imbalance_ratio=imbalance_ratio,
        mid_price_logodds=mid_price_logodds,
        spread_logodds=spread_logodds,
    )
