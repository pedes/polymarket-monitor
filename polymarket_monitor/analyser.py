"""Computes divergence between Polymarket implied probability and NOAA implied probability."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class DivergenceResult:
    market_id: str
    question: str
    polymarket_prob: float   # 0–100 scale
    noaa_prob: float         # 0–100 scale
    divergence: float        # absolute difference in percentage points
    direction: str           # "overpriced" | "underpriced" | "aligned"


def compute_divergence(
    market_id: str,
    question: str,
    yes_price: float,          # CLOB midpoint, 0–1
    noaa_implied_prob: float,  # 0–1 from NOAA heuristics
) -> DivergenceResult:
    """
    Convert both probabilities to percentage points and compute absolute divergence.

    Args:
        market_id: Polymarket market identifier.
        question: Human-readable market question.
        yes_price: Polymarket YES midpoint price in [0, 1].
        noaa_implied_prob: NOAA-derived probability in [0, 1].

    Returns:
        DivergenceResult with divergence in percentage points.
    """
    poly_pct = yes_price * 100.0
    noaa_pct = noaa_implied_prob * 100.0
    divergence = abs(poly_pct - noaa_pct)

    if poly_pct > noaa_pct + 1:
        direction = "overpriced"   # market thinks more likely than NOAA
    elif noaa_pct > poly_pct + 1:
        direction = "underpriced"  # market thinks less likely than NOAA
    else:
        direction = "aligned"

    return DivergenceResult(
        market_id=market_id,
        question=question,
        polymarket_prob=poly_pct,
        noaa_prob=noaa_pct,
        divergence=divergence,
        direction=direction,
    )


def exceeds_threshold(result: DivergenceResult, threshold: float) -> bool:
    """Return True if divergence is at or above the threshold (in percentage points)."""
    return result.divergence >= threshold


def format_divergence(result: DivergenceResult) -> str:
    return (
        f"[{result.direction.upper()}] {result.question}\n"
        f"  Polymarket: {result.polymarket_prob:.1f}%  |  "
        f"NOAA implied: {result.noaa_prob:.1f}%  |  "
        f"Divergence: {result.divergence:.1f}pp"
    )
