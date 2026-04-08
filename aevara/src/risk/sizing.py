# @module: aevara.src.risk.sizing
# @deps: aevara.src.utils.math
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Position sizing adaptativo baseado em conviccao do sinal
#           (log-odds), drawdown atual, e regime de mercado.

from __future__ import annotations

from dataclasses import dataclass
from aevara.src.utils.math import clip, sigmoid


@dataclass(frozen=True, slots=True)
class SizingResult:
    """Resultado do calculo de tamanho de posicao."""
    size_pct: float        # % do capital alocado
    side: str              # "long" ou "short"
    rationale: str


def adaptive_size(
    logodds: float,
    drawdown_pct: float = 0.0,
    max_drawdown: float = 4.8,
    base_size: float = 2.0,  # % do capital base
    conviction_multiplier: float = 5.0,
) -> SizingResult:
    """
    Position sizing adaptativo:
    - Sinal mais forte = tamanho maior (bounded)
    - Drawdown maior = tamanho menor (reducao nao linear)
    - Sinal proximo de zero = no position

    Formula:
    conviction = sigmoid(|L| * k) - 0.5  # [0, 0.5]
    drawdown_reduction = 1 - (DD / max_DD)^2  # quadratic reduction
    size = base_size * conviction * 2 * drawdown_reduction

    Args:
        logodds: Sinal agregado em log-odds
        drawdown_pct: Drawdown atual (% do capital)
        max_drawdown: Limite maximo de drawdown (%)
        base_size: Tamanho base da posicao (% capital)
        conviction_multiplier: Multiplicador para converter logodds -> conviction

    Returns:
        SizingResult com tamanho, lado, e rationale
    """
    abs_L = abs(logodds)

    # Conviction from log-odds: sigmoid scaled to [0, 1]
    conviction = (sigmoid(abs_L * conviction_multiplier) - 0.5) * 2.0

    # Drawdown reduction: quadratic penalty as DD approaches max
    dd_ratio = drawdown_pct / max_drawdown if max_drawdown > 0 else 0.0
    dd_reduction = 1.0 - dd_ratio ** 2
    dd_reduction = clip(dd_reduction, 0.0, 1.0)

    # Minimum logodds threshold for entry
    if abs_L < 0.5:
        return SizingResult(
            size_pct=0.0,
            side="flat",
            rationale=f"Signal too weak: |L|={abs_L:.3f} < 0.5",
        )

    size = base_size * conviction * dd_reduction
    size = clip(size, 0.0, base_size * 2.0)  # Cap at 2x base

    side = "long" if logodds > 0 else "short"

    return SizingResult(
        size_pct=round(size, 4),
        side=side,
        rationale=f"L={logodds:.3f}, conviction={conviction:.3f}, DD_reduction={dd_reduction:.3f} -> size={size:.4f}%",
    )
