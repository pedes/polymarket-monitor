"""Tests for the analyser module."""
import pytest
from polymarket_monitor.analyser import (
    compute_divergence,
    exceeds_threshold,
    format_divergence,
    DivergenceResult,
)


class TestComputeDivergence:
    def test_basic_overpriced(self):
        result = compute_divergence("mkt1", "Will it rain?", yes_price=0.80, noaa_implied_prob=0.40)
        assert result.polymarket_prob == pytest.approx(80.0)
        assert result.noaa_prob == pytest.approx(40.0)
        assert result.divergence == pytest.approx(40.0)
        assert result.direction == "overpriced"

    def test_basic_underpriced(self):
        result = compute_divergence("mkt2", "Hurricane landfall?", yes_price=0.20, noaa_implied_prob=0.70)
        assert result.divergence == pytest.approx(50.0)
        assert result.direction == "underpriced"

    def test_aligned(self):
        result = compute_divergence("mkt3", "Snow in Denver?", yes_price=0.55, noaa_implied_prob=0.56)
        assert result.divergence == pytest.approx(1.0)
        assert result.direction == "aligned"

    def test_zero_yes_price(self):
        result = compute_divergence("mkt4", "Tornado?", yes_price=0.0, noaa_implied_prob=0.0)
        assert result.divergence == pytest.approx(0.0)
        assert result.direction == "aligned"

    def test_full_divergence(self):
        result = compute_divergence("mkt5", "Rain?", yes_price=1.0, noaa_implied_prob=0.0)
        assert result.divergence == pytest.approx(100.0)
        assert result.direction == "overpriced"

    def test_result_market_id_preserved(self):
        result = compute_divergence("unique-id-xyz", "Test?", yes_price=0.5, noaa_implied_prob=0.5)
        assert result.market_id == "unique-id-xyz"
        assert result.question == "Test?"


class TestExceedsThreshold:
    def _make_result(self, divergence: float) -> DivergenceResult:
        return DivergenceResult(
            market_id="x",
            question="Q?",
            polymarket_prob=divergence,
            noaa_prob=0.0,
            divergence=divergence,
            direction="overpriced",
        )

    def test_exceeds(self):
        assert exceeds_threshold(self._make_result(25.0), 20.0) is True

    def test_exactly_at_threshold(self):
        assert exceeds_threshold(self._make_result(20.0), 20.0) is True

    def test_below_threshold(self):
        assert exceeds_threshold(self._make_result(19.9), 20.0) is False

    def test_zero_threshold_always_fires(self):
        assert exceeds_threshold(self._make_result(0.1), 0.0) is True


class TestFormatDivergence:
    def test_format_contains_key_fields(self):
        result = compute_divergence("mkt6", "Will it snow?", yes_price=0.30, noaa_implied_prob=0.60)
        formatted = format_divergence(result)
        assert "UNDERPRICED" in formatted
        assert "30.0%" in formatted
        assert "60.0%" in formatted
        assert "30.0pp" in formatted

    def test_format_overpriced_label(self):
        result = compute_divergence("mkt7", "Heat wave?", yes_price=0.90, noaa_implied_prob=0.10)
        assert "OVERPRICED" in format_divergence(result)

    def test_format_includes_question(self):
        result = compute_divergence("m", "Unique question text?", yes_price=0.5, noaa_implied_prob=0.5)
        assert "Unique question text?" in format_divergence(result)
